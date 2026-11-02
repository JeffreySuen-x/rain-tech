"""Bounded agricultural material extraction and document exports.
See server/AGRICULTURE_SOURCES.json for dependency and license information.
"""
from io import BytesIO
from pathlib import Path
import hashlib
import json
import struct
import tempfile
import zipfile
import zlib
from .agriculture import AgricultureError, MAX_FILE
MAX_TEXT = 200000

def extract_segments(path):
    """Use established file libraries; locators describe extraction, not page guesses."""
    suffix = path.suffix.lower()
    segments, warnings = [], []
    def add(locator, text):
        if text.strip():
            if len(segments) >= 10000:
                raise ValueError('资料段落超过 1 万段，请拆分；没有保存部分正文')
            segments.append({'locator': locator, 'text': text.strip()})
    if suffix in {'.txt', '.md', '.csv'}:
        for i, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
            add(f'L{i}', line)
    elif suffix in {'.docx', '.pptx'}:
        with zipfile.ZipFile(path) as archive:
            if sum(item.file_size for item in archive.infolist()) > 100 * 1024 * 1024:
                raise ValueError('Office 文件解压后过大，请拆分资料')
        if suffix == '.docx':
            from docx import Document
            from docx.table import Table
            for i, block in enumerate(Document(path).iter_inner_content(), 1):
                if isinstance(block, Table):
                    for r, row in enumerate(block.rows, 1):
                        add(f'block:{i}/row:{r}', ' | '.join(cell.text for cell in row.cells))
                else:
                    add(f'block:{i}', block.text)
            warnings.append('Word 按段落/表格定位；图片、页眉页脚和嵌入对象需回原件核对。')
        else:
            from pptx import Presentation
            def shapes(items, prefix):
                for j, shape in enumerate(items, 1):
                    at = f'{prefix}/shape:{j}'
                    if shape.has_text_frame:
                        add(at, shape.text)
                    if shape.has_table:
                        for r, row in enumerate(shape.table.rows, 1):
                            add(f'{at}/row:{r}', ' | '.join(cell.text for cell in row.cells))
                    if hasattr(shape, 'shapes'):
                        shapes(shape.shapes, at)
            for i, slide in enumerate(Presentation(path).slides, 1):
                shapes(slide.shapes, f'slide:{i}')
            warnings.append('已提取幻灯片文本和表格；图表、图片与动画需回原件核对。')
    elif suffix == '.pdf':
        from pypdf import PdfReader
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise ValueError('PDF 已加密，请提供可读取版本')
        for i, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ''
            add(f'page:{i}', text)
            if not text.strip():
                warnings.append(f'第 {i} 页没有可提取文字，可能是扫描页；需 OCR 或人工核对。')
        warnings.append('PDF 表格的列序、跨栏和图中文字需回原件核对。')
    else:
        raise ValueError('目前支持 UTF-8 TXT/MD/CSV、DOCX、PPTX 和文字 PDF；请转换旧版 Office 或图片资料')
    if not segments:
        raise ValueError('未提取到正文，可能是扫描/图片资料；请提供文字版或先核对 OCR 结果')
    if sum(len(item['text']) for item in segments) > MAX_TEXT:
        raise ValueError('资料正文超过 20 万字，请按产品拆分；没有截断或保存部分正文')
    return segments, warnings



def reject(message, status=415):
    raise AgricultureError('unsupported_media', message, status)


def preflight_office(raw):
    try:
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            entries = archive.infolist()
            if len(entries) > 1000 or sum(e.file_size for e in entries) > 40 * 1024 * 1024:
                reject('办公文件解压后过大。')
            if len({e.filename for e in entries}) != len(entries):
                reject('办公文件含重复条目。')
            for e in entries:
                if '..' in Path(e.filename).parts or e.filename.startswith('/') or '\\' in e.filename or e.flag_bits & 1 or 'vbaproject' in e.filename.lower():
                    reject('办公文件结构不安全或包含宏。')
                if e.file_size > 1024 * 1024 and e.file_size > max(1, e.compress_size) * 100:
                    reject('办公文件压缩比超出安全限制。')
    except (zipfile.BadZipFile, RuntimeError):
        reject('办公文件已损坏。')


def _extract_local(raw, name, directory):
    suffix = Path(name).suffix.lower()
    if suffix not in {'.txt', '.md', '.csv', '.docx', '.pptx', '.pdf'}:
        reject('仅支持UTF-8 TXT/MD/CSV、DOCX/PPTX和文字PDF。')
    if suffix in {'.docx', '.pptx'}:
        preflight_office(raw)
    if suffix == '.pdf':
        from pypdf import PdfReader
        try:
            reader = PdfReader(BytesIO(raw))
            if reader.is_encrypted or len(reader.pages) > 200:
                reject('PDF必须可读取且不超过200页。')
        except AgricultureError:
            raise
        except Exception:
            reject('PDF已损坏。')
    try:
        path = Path(directory) / ('material' + suffix)
        path.write_bytes(raw)
        segments, warnings = extract_segments(path)
    except Exception:
        reject('文档无法安全解析；请提供完整可读取的文字文件。')
    if any('\x00' in item['text'] for item in segments):
        reject('资料含不支持的二进制字符。')
    return segments, warnings


MATERIAL_TIMEOUT = 15
MATERIAL_OUTPUT_LIMIT = 4 * 1024 * 1024

def _validate_extracted(value):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError()
    segments, warnings = value
    if not isinstance(segments, list) or not 0 < len(segments) <= 10000:
        raise ValueError()
    total = 0
    for item in segments:
        if not isinstance(item, dict) or set(item) != {'locator', 'text'}:
            raise ValueError()
        if not isinstance(item['locator'], str) or len(item['locator']) > 1000 or not isinstance(item['text'], str) or '\x00' in item['text']:
            raise ValueError()
        total += len(item['text'])
    if total > MAX_TEXT or not isinstance(warnings, list) or len(warnings) > 256 or any(not isinstance(w, str) or len(w) > 2000 for w in warnings):
        raise ValueError()
    return segments, warnings


def extract(raw, name):
    """Parse untrusted documents in a disposable bounded process."""
    import os
    import subprocess
    import sys
    import threading
    import time
    suffix = Path(name).suffix.lower()
    if not isinstance(raw, bytes) or not raw or len(raw) > 20 * 1024 * 1024 or suffix not in {'.txt', '.md', '.csv', '.docx', '.pptx', '.pdf'}:
        reject('文档无法安全解析；请提供完整可读取的文字文件。')
    deadline = time.monotonic() + MATERIAL_TIMEOUT
    with tempfile.TemporaryDirectory(prefix='shuyu-document-') as directory:
        return _extract_process(raw, suffix, directory, deadline)


def _extract_process(raw, suffix, directory, deadline):
    import os
    import subprocess
    import sys
    import threading
    import time
    try:
        process = subprocess.Popen([sys.executable, '-m', 'server.material_worker'],
            cwd=str(Path(__file__).resolve().parent.parent), stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env={k:v for k,v in os.environ.items() if k in ('SYSTEMROOT','WINDIR','PATH','LANG','LC_ALL')})
    except OSError:
        reject('文档解析服务暂不可用。', 503)
    output, errors = [], []
    def write():
        try:
            process.stdin.write(json.dumps({'suffix': suffix, 'directory': directory}).encode() + b'\n' + raw)
            process.stdin.close()
        except (OSError, ValueError): errors.append(True)
    def read():
        try: output.append(process.stdout.read(MATERIAL_OUTPUT_LIMIT + 1))
        except (OSError, ValueError): errors.append(True)
    threads = [threading.Thread(target=write, name='material-input'), threading.Thread(target=read, name='material-output')]
    try:
        for thread in threads: thread.start()
        while process.poll() is None:
            if time.monotonic() >= deadline: raise ValueError()
            time.sleep(.025)
        for thread in threads: thread.join(.5)
        if time.monotonic() >= deadline or process.returncode or errors or not output or len(output[0]) > MATERIAL_OUTPUT_LIMIT:
            raise ValueError()
        value = _validate_extracted(json.loads(output[0]))
        if time.monotonic() >= deadline: raise ValueError()
        return value
    except Exception:
        reject('文档无法安全解析；请提供完整可读取的文字文件。')
    finally:
        if process.poll() is None:
            process.terminate()
            try: process.wait(timeout=.5)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()
        else: process.wait()
        for thread in threads:
            if thread.ident is not None: thread.join(1)
        process.stdin.close(); process.stdout.close()


def validate_png(raw):
    """Decode bounded non-interlaced 8-bit PNG scanlines without native codecs.

    CRCs, chunk ordering, zlib EOF, exact scanline count, filtering, and decoded
    pixel bounds are checked. Unsupported PNG variants fail explicitly.
    """
    if not raw.startswith(b'\x89PNG\r\n\x1a\n'):
        reject('当前安全解码器支持8位非交错PNG；JPEG/WebP请转换后上传。')
    offset, image, end, header = 8, bytearray(), False, None
    seen_idat = False
    while offset < len(raw):
        if offset + 12 > len(raw):
            reject('PNG结构不完整。')
        size = struct.unpack('>I', raw[offset:offset+4])[0]
        kind = raw[offset+4:offset+8]
        if size > MAX_FILE or offset + size + 12 > len(raw):
            reject('PNG块长度无效。')
        data = raw[offset+8:offset+8+size]
        crc = struct.unpack('>I', raw[offset+8+size:offset+12+size])[0]
        if zlib.crc32(kind + data) & 0xffffffff != crc:
            reject('PNG校验失败。')
        if header is None and kind != b'IHDR':
            reject('PNG缺少头部。')
        if kind == b'IHDR':
            if header is not None or size != 13:
                reject('PNG头部无效。')
            width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', data)
            if not width or not height or width * height > 25000000 or depth != 8 or color not in {0, 2, 4, 6} or compression or filtering or interlace:
                reject('支持8位非交错灰度/RGB/RGBA PNG，最多2500万像素。')
            header = width, height, {0: 1, 2: 3, 4: 2, 6: 4}[color]
        elif kind == b'IDAT':
            seen_idat = True
            image.extend(data)
        elif kind == b'IEND':
            if size or not seen_idat or offset + 12 != len(raw):
                reject('PNG结尾无效。')
            end = True
            break
        elif kind[:1].isupper() and kind not in {b'PLTE'}:
            reject('PNG包含不支持的必要块。')
        offset += size + 12
    if not end or not header:
        reject('PNG缺少结尾。')
    width, height, channels = header
    row_size = width * channels
    expected = height * (row_size + 1)
    # A large valid image still has a bounded ~100MB transient decode budget.
    inflater = zlib.decompressobj()
    try:
        decoded = inflater.decompress(bytes(image), expected + 1)
        if len(decoded) != expected or not inflater.eof or inflater.unused_data or inflater.unconsumed_tail:
            reject('PNG像素数据长度无效。')
    except zlib.error:
        reject('PNG像素解码失败。')
    previous = bytearray(row_size)
    for row in range(height):
        start = row * (row_size + 1)
        filter_type = decoded[start]
        if filter_type > 4:
            reject('PNG过滤器无效。')
        pixels = bytearray(decoded[start + 1:start + 1 + row_size])
        if filter_type:
            for i, value in enumerate(pixels):
                a, b, c = pixels[i-channels] if i >= channels else 0, previous[i], previous[i-channels] if i >= channels else 0
                if filter_type == 1:
                    add = a
                elif filter_type == 2:
                    add = b
                elif filter_type == 3:
                    add = (a + b) // 2
                else:
                    p = a + b - c
                    pa, pb, pc = abs(p-a), abs(p-b), abs(p-c)
                    add = a if pa <= pb and pa <= pc else b if pb <= pc else c
                pixels[i] = (value + add) & 255
        previous = pixels
    return 'image/png'


def validate_audio(raw, name):
    suffix = Path(name).suffix.lower()
    if suffix == '.wav':
        import wave
        try:
            with wave.open(BytesIO(raw), 'rb') as audio:
                if audio.getnchannels() not in {1, 2} or not 8000 <= audio.getframerate() <= 192000 or audio.getnframes() / audio.getframerate() > 600:
                    reject('WAV需为1/2声道且时长不超过10分钟。')
                if len(audio.readframes(audio.getnframes())) != audio.getnframes() * audio.getnchannels() * audio.getsampwidth():
                    reject('WAV音频数据不完整。')
        except (wave.Error, EOFError):
            reject('WAV音频无效。')
        return 'audio/wav'
    supported = {'.mp3': ('audio/mpeg', raw.startswith((b'ID3', b'\xff\xfb', b'\xff\xf3', b'\xff\xf2'))), '.ogg': ('audio/ogg', raw.startswith(b'OggS')), '.flac': ('audio/flac', raw.startswith(b'fLaC')), '.webm': ('audio/webm', raw.startswith(b'\x1aE\xdf\xa3')), '.m4a': ('audio/mp4', len(raw) > 12 and raw[4:8] == b'ftyp')}
    mime, valid = supported.get(suffix, (None, False))
    if not valid:
        reject('音频容器或扩展名不受支持。')
    return mime


def export_bytes(report, format, image_resolver=None):
    if format == "md":
        return export_markdown(report)
    if report.get("document"):
        return export_document(report, format, image_resolver)
    out = BytesIO()
    references = ['来源：' + encode_source(s) for s in report.get('sources', [])]
    if format == 'docx':
        from docx import Document
        doc = Document()
        doc.add_heading(report['title'], 0)
        for paragraph in report['body'].splitlines():
            doc.add_paragraph(paragraph)
        for reference in references:
            doc.add_paragraph(reference)
        doc.save(out)
    elif format == 'pptx':
        from pptx import Presentation
        presentation = Presentation()
        paragraphs = report['body'].splitlines() + references
        chunks = [paragraphs[i:i+10] for i in range(0, len(paragraphs), 10)] or [[]]
        for lines in chunks:
            slide = presentation.slides.add_slide(presentation.slide_layouts[1])
            slide.shapes.title.text = report['title']
            slide.placeholders[1].text = '\n'.join(lines)
        presentation.save(out)
    else:
        reject('导出仅支持docx/pptx。')
    return out.getvalue()


def encode_source(source):
    return json.dumps(source, ensure_ascii=False, sort_keys=True)


def validate_image(raw):
    """Use the reviewed installed codec's public API, with full pixel decoding."""
    from PIL import Image, UnidentifiedImageError
    import warnings
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as image:
                if image.format not in {'PNG', 'JPEG', 'WEBP'} or image.width < 1 or image.height < 1 or image.width * image.height > 25000000 or getattr(image, 'n_frames', 1) != 1:
                    reject('图片仅支持单帧PNG/JPEG/WebP，且不得超过2500万像素。')
                format = image.format
                image.verify()
            # verify() checks container structure; load() also decodes pixels.
            with Image.open(BytesIO(raw)) as image:
                image.load()
                if image.width * image.height > 25000000:
                    reject('图片像素超出上限。')
            return {'PNG': 'image/png', 'JPEG': 'image/jpeg', 'WEBP': 'image/webp'}[format]
    except AgricultureError:
        raise
    except Exception:
        reject('图片损坏、解码失败或超出安全限制。')


def outbound_image(raw):
    """Decode, orient, and rebuild pixels without carrying source metadata."""
    from PIL import Image, ImageOps
    validate_image(raw)
    with Image.open(BytesIO(raw)) as image:
        image=ImageOps.exif_transpose(image)
        transparent=image.mode in ('RGBA','LA') or 'transparency' in image.info
        converted=image.convert('RGBA' if transparent else 'RGB')
        clean=Image.new(converted.mode,converted.size)
        clean.paste(converted)
        output=BytesIO()
        clean.save(output,format='PNG')
        content=output.getvalue()
        if len(content)>MAX_FILE:raise AgricultureError('too_large','处理后图片过大。',413)
        return content,'image/png',{'originalHash':hashlib.sha256(raw).hexdigest(),'derivedHash':hashlib.sha256(content).hexdigest(),'method':'pillow-exif-transpose-pixel-reencode-png-v1','width':clean.width,'height':clean.height}


def report_date(at):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return '未记录' if at is None else datetime.fromtimestamp(at, ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M')


def report_excerpt(text, maximum=240):
    text = str(text or '')
    return text if len(text) <= maximum else text[:maximum]+'…（已截短，完整内容见工作台同报告）'


def observation_groups(document):
    groups = {}
    for row in document['observations']:
        groups.setdefault((row['deviceId'], row['metric'], row.get('unit'), row['source']), []).append(row)
    return groups


def series_title(key):
    metric = {'temperature':'空气温度','humidity':'空气湿度','soil_moisture':'土壤水分'}.get(key[1], str(key[1]))
    unit = {'celsius':'°C','percent':'%'}.get(key[2], str(key[2] or '单位未提供'))
    source = {'demo':'演示模拟数据','test':'测试上报数据','device':'设备上报数据'}.get(key[3], str(key[3]))
    return metric+'（'+unit+'） / '+source+' / 设备'+str(key[0])[-8:]


def office_lines(text, width=38):
    import re
    tokens=re.findall(r'[0-9a-fA-F]{64}|\d{4}-\d{2}-\d{2} \d{2}:\d{2}|.', text)
    result=[]
    current=''
    for token in tokens:
        if current and len(current)+len(token)>width:
            result.append(current);current=''
        current+=token
    if current:result.append(current)
    return result or ['']


def readable_limitation(text):
    import re
    return re.sub(r'(?<![\d.])1[0-9]{9}(?:\.[0-9]+)?', lambda match: report_date(float(match.group(0))), str(text)).replace(' Unix秒', '（上海时间）')


def document_sections(report):
    """Readable Office projection; the immutable document remains the full evidence."""
    from .agriculture import digest
    doc = report['document']
    summary = doc['summary']
    sections = [('摘要', [f"所选任务：{summary['taskCount']}；已完成：{summary['completedTaskCount']}；完成记录：{summary['recordCount']}", f"统计时段：{report_date(doc['period']['from'])} — {report_date(doc['period']['to'])}（上海时间）", f"生成时间：{report_date(doc['generatedAt'])}（上海时间）"])]
    tasks = doc['tasks']
    sections.append(('所选任务', [report_excerpt(t['title'])+' | '+{'completed':'已完成','open':'待处理'}.get(t['status'],t['status'])+' | 完成：'+report_date(t.get('completedAt')) for t in tasks[:20]] or ['暂无所选任务。']))
    groups = observation_groups(doc)
    trends=[]
    for key, rows in list(groups.items())[:12]:
        numeric=[r['value'] for r in rows if type(r.get('value')) in (int,float)]
        value_range=('；范围 '+str(min(numeric))+'—'+str(max(numeric))) if numeric else '；无数值数据'
        trends.append(series_title(key)+'；'+str(len(rows))+'点；'+report_date(min(r['observedAt'] for r in rows))+' — '+report_date(max(r['observedAt'] for r in rows))+value_range)
    sections.append(('监测摘要',trends or ['该时段暂无监测数据。']))
    records=[source for source in doc['sources'] if source.get('kind')=='activity_record']
    sections.append(('完成记录摘要',[report_excerpt(source.get('excerpt', '')) for source in records[:20]] or ['暂无完成记录。']))
    source_groups={}
    for source in doc['sources']:
        key=(source.get('kind','unknown'),source.get('origin',source.get('source','')))
        source_groups[key]=source_groups.get(key,0)+1
    labels={'activity_record':'完成记录','observation':'监测读数','asset':'关联资产','knowledge':'知识资料','live_demo':'模拟序列'}
    origins={'demo':'演示模拟','test':'测试上报','device':'设备上报','user':'用户提供','':'未标记'}
    evidence=[labels.get(kind,kind)+' / '+origins.get(origin,origin)+'：'+str(count)+'项' for (kind,origin),count in list(source_groups.items())[:12]]
    evidence += ['设备标识 '+str(device)[-8:]+'：'+str(device) for device in dict.fromkeys(key[0] for key in groups)]
    evidence += ['报告编号：'+str(report.get('id','未提供')), '文档版本：'+str(doc['schemaVersion']), '冻结快照 SHA-256：'+digest(doc)]
    for photo in doc['photos']:
        evidence.append('照片：'+photo['name']+'；来源：'+origins.get(photo.get('origin',''),photo.get('origin','未标记'))+'；SHA-256：'+photo['sha256'])
    for source in doc['sources']:
        if source.get('kind')=='live_demo':
            coverage=source.get('coverage',{})
            evidence.append('模拟批次 version='+str(source.get('version'))+'；样本数='+str(source.get('sampleCount'))+'；覆盖 '+report_date(coverage.get('from'))+' — '+report_date(coverage.get('to'))+'；SHA-256：'+str(source.get('sourceHash','未提供')))
    evidence.append('本文件为报告摘要：图表使用所展示系列的全部冻结样本；逐点记录、完整来源及未展开文字保留在工作台同一报告（报告编号：'+str(report.get('id','未提供'))+'），本文件不逐条附印。')
    for label,total,shown in [('监测系列',len(groups),12),('任务',len(tasks),20),('完成记录',len(records),20),('来源分组',len(source_groups),12)]:
        if total>shown:evidence.append(label+'已展示 '+str(shown)+' / '+str(total)+'；其余请在工作台同报告查看。')
    sections.append(('依据与限制',evidence+[readable_limitation(line) for line in doc['limitations']]))
    return sections


def report_charts(document):
    """Pixel charts group by device, metric, unit AND source; raw values are also printed."""
    from PIL import Image, ImageDraw, ImageFont
    from datetime import datetime
    from zoneinfo import ZoneInfo
    try:
        font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf', 20)
    except OSError:
        font = ImageFont.load_default(size=20)
    groups = {}
    for row in document['observations']:
        if type(row.get('value')) not in (float, int):
            continue
        groups.setdefault((row['deviceId'], row['metric'], row.get('unit'), row['source']), []).append(row)
    for key, rows in list(groups.items())[:12]:
        rows = sorted(rows, key=lambda r:r['observedAt'])
        image = Image.new('RGB', (1000, 420), 'white')
        draw = ImageDraw.Draw(image)
        lo, hi = min(r['value'] for r in rows), max(r['value'] for r in rows)
        if hi == lo: lo, hi = lo-1, hi+1
        start, end = rows[0]['observedAt'], rows[-1]['observedAt']
        display_unit = {'celsius':'°C', 'percent':'%'}.get(key[2], key[2] or 'unit unavailable')
        draw.text((90,8), display_unit, fill='black', font=font)
        draw.line((90,40,90,340,950,340), fill='black', width=2)
        for step in range(5):
            value = lo+(hi-lo)*step/4
            y = 340-step*75
            draw.text((8,y-10), f'{value:.3g}', fill='black', font=font)
            draw.line((90,y,950,y), fill='#dddddd')
        points = [(90+(r['observedAt']-start)/max(1,end-start)*860, 340-(r['value']-lo)/(hi-lo)*300) for r in rows]
        if len(points)>1: draw.line(points, fill='#216b52', width=3)
        for x,y in points: draw.ellipse((x-3,y-3,x+3,y+3), fill='#216b52')
        def axis_time(at):
            return datetime.fromtimestamp(at, ZoneInfo('Asia/Shanghai')).strftime('%m-%d %H:%M')
        draw.text((90,365), axis_time(start), fill='black', font=font)
        draw.text((795,365), axis_time(end), fill='black', font=font)
        draw.text((390,395), 'Asia/Shanghai', fill='black', font=font)
        out=BytesIO();image.save(out,format='PNG')
        yield series_title(key), out.getvalue()


def export_document(report, format, image_resolver):
    document = report['document']
    images=[]
    for photo in document['photos']:
        if image_resolver is None:
            raise AgricultureError('source_unavailable', '报告照片缺少受信任资产读取器。', 409)
        raw=image_resolver(photo)
        validate_image(raw)
        # Office consistently supports PNG; source hash was checked before this conversion.
        raw, _, _ = outbound_image(raw)
        images.append((report_excerpt(photo['caption'])+' | 记录时间：'+report_date(photo['recordCompletedAt'])+'（上海时间）',raw))
    charts=list(report_charts(document))
    out=BytesIO()
    if format=='docx':
        from docx import Document
        from docx.shared import Inches
        word=Document();word.add_heading(report['title'],0)
        for title, lines in document_sections(report):
            word.add_heading(title,1)
            for line in lines: word.add_paragraph(line)
        word.add_heading('关联照片',1)
        if not images: word.add_paragraph('暂无关联照片。')
        for caption,raw in images:
            word.add_picture(BytesIO(raw),width=Inches(5.6));word.add_paragraph(caption)
        for caption,raw in charts:
            word.add_heading('监测趋势：'+caption,2);word.add_picture(BytesIO(raw),width=Inches(5.6))
        word.save(out)
    elif format=='pptx':
        from pptx import Presentation
        from pptx.util import Inches, Pt
        deck=Presentation();deck.slide_width=Inches(13.333);deck.slide_height=Inches(7.5)
        def text_slide(title, lines):
            slide=deck.slides.add_slide(deck.slide_layouts[1]);slide.shapes.title.text=title
            frame=slide.placeholders[1].text_frame;frame.clear();frame.word_wrap=True
            for i,line in enumerate(lines):
                p=frame.paragraphs[0] if i==0 else frame.add_paragraph();p.text=line;p.font.size=Pt(17)
            return slide
        text_slide(report['title'], ['正式事实报告', document['timezone']])
        for title, lines in document_sections(report):
            # Bound text per slide, including long evidence JSON and record notes.
            wrapped=[part for line in lines for part in office_lines(line)]
            for i in range(0,len(wrapped),9):text_slide(title, wrapped[i:i+9])
        if not images:text_slide('关联照片',['暂无关联照片。'])
        from PIL import Image
        for title,raw in images+charts:
            slide=text_slide('关联照片' if (title,raw) in images else '监测趋势',[title[:38]])
            with Image.open(BytesIO(raw)) as image:
                width,height=image.size
            scale=min(10.5/width,4.6/height)
            slide.shapes.add_picture(BytesIO(raw), Inches((13.333-width*scale)/2), Inches(2.3), width=Inches(width*scale), height=Inches(height*scale))
            if len(title)>38:
                lines=[title[i:i+38] for i in range(0,len(title),38)]
                for i in range(0,len(lines),9):text_slide('完整图注',lines[i:i+9])
        deck.save(out)
    else:
        reject('导出仅支持docx/pptx。')
    return out.getvalue()


def export_markdown(report):
    """Text-only allowlisted projection of frozen evidence, never asset URLs."""
    import html
    import re
    def safe(value):
        value = html.escape(str(value if value is not None else '未记录'), quote=False)
        return re.sub(r'([\\`*_{}\[\]()#+.!|>~-])', r'\\\1', value).replace('\r', '').replace('\n', ' / ')
    statuses = {'completed': '已完成', 'open': '待处理'}
    origins = {'demo': '演示模拟', 'test': '测试上报', 'device': '设备上报', 'user': '用户提供'}
    qualities = {'simulated': '模拟数据', 'reported': '上报数据'}
    lines = ['# '+safe(report['title']), '']
    def section(title, values):
        lines.extend(['## '+title, ''])
        lines.extend('- '+safe(value) for value in values)
        lines.append('')
    doc = report.get('document')
    if doc:
        summary = doc['summary']
        section('摘要与范围', [
            '生成时间：'+report_date(doc['generatedAt'])+'（上海时间）',
            '统计时段：'+report_date(doc['period']['from'])+' — '+report_date(doc['period']['to'])+'（上海时间）',
            '地块范围：'+('所选地块（标识末8位：'+str(report['plotId'])[-8:]+'）' if report.get('plotId') else '园区范围'),
            f"所选任务：{summary['taskCount']}；已完成：{summary['completedTaskCount']}；完成记录：{summary['recordCount']}"])
        section('任务完成情况', [str(t['title'])+'；状态：'+statuses.get(t['status'], str(t['status']))+'；完成时间：'+report_date(t.get('completedAt')) for t in doc['tasks']] or ['暂无所选任务。'])
        section('已有完成记录', [s.get('excerpt', '') for s in doc['sources'] if s.get('kind')=='activity_record'] or ['暂无完成记录。'])
        section('监测事实', [series_title((r['deviceId'],r['metric'],r.get('unit'),r['source']))+'；时间：'+report_date(r['observedAt'])+'；读数：'+str(r['value'])+'；质量：'+qualities.get(r.get('quality'), str(r.get('quality','未记录'))) for r in doc['observations']] or ['该时段暂无监测数据。'])
        section('照片元信息（不含原图）', [str(p['name'])+'；说明：'+str(p['caption'])+'；记录时间：'+report_date(p['recordCompletedAt'])+'；来源：'+origins.get(p.get('origin'), str(p.get('origin','未标记')))+'；内容校验值（SHA-256）：'+p['sha256'] for p in doc['photos']] or ['暂无关联照片。'])
        section('限制', [readable_limitation(v) for v in doc['limitations']]+['本文件只包含事实快照与照片元信息，不含原图。'])
    else:
        section('历史报告摘要', report.get('body','').splitlines() or ['暂无正文。'])
        section('范围与限制', ['历史报告未保存结构化文档，生成时间、统计范围及照片信息以原正文为准；不推断缺失事实。'])
    labels = {'kind': '类型', 'id': '记录编号', 'title': '标题', 'origin': '原始来源', 'source': '数据来源', 'version': '版本', 'sourceHash': '内容校验值', 'excerpt': '记录摘要'}
    sources = ['；'.join(labels[key]+'：'+str(source[key]) for key in labels if key in source) for source in (doc.get('sources',[]) if doc else report.get('sources',[]))]
    if report.get('plotId'):
        sources.insert(0, '地块完整标识：'+str(report['plotId']))
    section('来源', sources or ['暂无来源。'])
    return ('\n'.join(lines)+'\n').encode('utf-8')
