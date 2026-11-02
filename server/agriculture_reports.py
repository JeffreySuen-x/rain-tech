"""Frozen facts for the existing report authority; no model invocation."""
import copy
import time
from .agriculture import AgricultureError, read, entities, device_readings, asset_content, digest


def freeze(db, owner, wid, plot_id, tasks, records, sources, root):
    now = time.time()
    start = now - 7 * 86400
    observations, photos, limits = [], [], []
    for device in entities(db, owner, wid, 'device'):
        if plot_id and device.get('plotId') != plot_id:
            continue
        found = device_readings(db, owner, device['id'], start=start, end=now)['observations']
        observations.extend({k: row.get(k) for k in ('id','deviceId','metric','value','unit','observedAt','source','sourceEventId','quality')} for row in found)
        if len(found) >= 1000:
            limits.append('设备 '+device['id']+' 达到读取上限，可能未覆盖全部时段。')
    from .agriculture_live_demo import view
    live = view(db, owner, wid, plot_id, at=now)
    live_samples = [sample for sample in (live or {}).get('samples', []) if start <= sample['observedAt'] <= now]
    for sample in live_samples:
        for metric, unit in (('temperature', '°C'), ('humidity', '%'), ('soil_moisture', '%')):
            if metric in sample:
                event_id='demo:'+str(live['version'])+':'+sample['plotId']+':'+str(sample['observedAt'])+':'+metric
                observations.append(dict(id=event_id, plotId=sample['plotId'], liveDemoVersion=live['version'], deviceId='demo:'+sample['plotId'], metric=metric, value=sample[metric], unit=unit, observedAt=sample['observedAt'], source='demo', sourceEventId=event_id, quality='simulated'))
    if live_samples:
        limits.append('既有模拟序列，最多每地块120点，非完整7日；实际覆盖 '+str(min(s['observedAt'] for s in live_samples))+' 至 '+str(max(s['observedAt'] for s in live_samples))+' Unix秒。')
    observations.sort(key=lambda row: (row['observedAt'], row['id']))
    if len(observations)>2000:
        observations=observations[-2000:]
        limits.append('监测记录超过2000条，仅冻结最新2000条；实际覆盖时间：'+str(observations[0]['observedAt'])+' 至 '+str(observations[-1]['observedAt'])+' Unix秒。')
    demo_assets={item.get('assetId') for item in (live or {}).get('cameras', [])+(live or {}).get('captures', [])}
    for record in records:
        for aid in record.get('assetIds', []):
            asset = read(db, owner, aid, 'asset', wid)
            if asset.get('kind') != 'image':
                continue
            if len(photos) >= 6:
                limits.append('关联照片超过6张，其余未纳入本报告。')
                break
            asset_content(db, owner, aid, root)
            is_demo=bool(asset.get('demoSourceAssetId') or aid in demo_assets)
            photos.append(dict(origin='demo' if is_demo else 'user', assetId=aid, name=asset['name'], sha256=asset['sha256'], version=asset['version'], recordId=record['id'], recordCompletedAt=record['completedAt'], caption=('演示图片：' if is_demo else '')+record['note']))
    frozen_sources = copy.deepcopy(sources)
    if live_samples:
        frozen_sources.append(dict(id='live-demo:'+wid, kind='live_demo', origin='demo', sampleCount=len(live_samples), title='既有模拟序列', version=live['version'], sourceHash=digest(live_samples), locator='live-demo:'+wid, coverage={'from':min(s['observedAt'] for s in live_samples),'to':max(s['observedAt'] for s in live_samples)}))
    for row in observations:
        frozen_sources.append(dict(id=row['id'], kind='observation', title='设备记录', sourceHash=digest(row), locator='device:'+row['deviceId'], excerpt=str(row['value'])+' '+str(row.get('unit') or ''), source=row['source']))
    for photo in photos:
        frozen_sources.append(dict(id=photo['assetId'], kind='asset', origin=photo['origin'], title=photo['name'], version=photo['version'], sourceHash=photo['sha256'], locator='asset:'+photo['assetId']))
    if not observations: limits.append('该时段暂无监测数据。')
    if any(not row.get('unit') for row in observations): limits.append('部分监测记录缺少单位，不推测单位。')
    if not photos: limits.append('暂无关联照片。')
    return dict(schemaVersion='agriculture.report.v1', generatedAt=now, timezone='Asia/Shanghai', period={'from':start, 'to':now}, summary=dict(taskCount=len(tasks), completedTaskCount=sum(t['status']=='completed' for t in tasks), recordCount=len(records)), tasks=[{k:t.get(k) for k in ('id','title','status','plotId','dueAt','completedAt')} for t in tasks], observations=observations, photos=photos, sources=frozen_sources, limitations=list(dict.fromkeys(limits)))


def photo_bytes(db, owner, wid, photo, root):
    try:
        asset = read(db, owner, photo['assetId'], 'asset', wid)
        if asset.get('kind') != 'image' or asset.get('sha256') != photo['sha256'] or asset.get('version') != photo['version']:
            raise ValueError('changed')
        path, _ = asset_content(db, owner, asset['id'], root)
        return path.read_bytes()
    except (AgricultureError, ValueError, KeyError):
        raise AgricultureError('source_unavailable', '报告照片来源已撤销、改变或不可用。', 409)


def validate_sources(db, owner, report):
    for source in report.get('sources', []):
        if source.get('kind') == 'knowledge':
            try:
                knowledge = read(db, owner, source['id'], 'knowledge', report['workspaceId'])
                read(db, owner, knowledge['assetId'], 'asset', report['workspaceId'])
                if (source.get('version') is not None and source['version'] != knowledge.get('version')) or (source.get('sourceHash') and source['sourceHash'] != knowledge.get('sourceHash')):
                    raise AgricultureError('source_unavailable', '报告知识来源版本已改变。', 409)
            except AgricultureError:
                raise AgricultureError('source_unavailable', '报告知识来源已撤销。', 409)


def present(db, owner, report, root):
    validate_sources(db, owner, report)
    result = copy.deepcopy(report)
    for photo in result.get('document', {}).get('photos', []):
        try:
            photo_bytes(db, owner, report['workspaceId'], photo, root)
            photo.update(available=True, contentUrl='/api/v1/assets/'+photo['assetId']+'/content')
        except AgricultureError:
            photo.update(available=False, contentUrl=None)
    return result


def present_collection(db, owner, report, root):
    """A revoked report must not disclose content or disable unrelated workspace UI."""
    try:
        return present(db, owner, report, root)
    except AgricultureError as error:
        if error.code != 'source_unavailable':
            raise
        return dict(id=report['id'], createdAt=report['createdAt'], title='来源不可用的报告', unavailable=True, reason='报告引用的来源已撤销或改变。')
