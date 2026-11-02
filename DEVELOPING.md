# 开发指南

先按README在仓库根目录安装依赖、构建前端、生成seed并启动。使用独立开发数据目录，避免测试影响日常资料。

## 日常开发

- 前端修改后运行`npm --prefix web run build`并刷新。桌面启动器提供的是构建后的页面。
- 后端修改后使用相同数据目录执行启动器`--stop`，再启动，避免重复worker。
- 热更新：API默认6480、Vite默认5180；API和worker使用相同的`SHUYU_PUBLIC_ORIGIN=http://127.0.0.1:5180`及DB/资产/secret配置，运行`npm --prefix web run dev`。Vite代理可通过`VITE_DEV_API_TARGET`指定。
- 修改样例后向新的目录生成seed；不要覆盖已有用户库。启动时可用`SHUYU_SEED_DIR`显式选择样例目录。

## Windows PowerShell

Windows完整运行尚未验收，以下是开发入口：

```powershell
py -3.11 -m venv server/.venv
.\server\.venv\Scripts\python.exe -m pip install -r server/requirements-lock.txt
npm --prefix runtime/dsh ci --ignore-scripts
npm --prefix web ci
npm --prefix web run build
.\server\.venv\Scripts\python.exe -m server.student_demo --output seed
$env:SHUYU_BUNDLE_ROOT = (Get-Location).Path
$env:SHUYU_DATA_DIR = Join-Path (Get-Location).Path '.local-data'
.\server\.venv\Scripts\python.exe desktop/shuyu_desktop.py
```

seed只生成一次。后续设置/停止在最后命令加`--setup`/`--stop`。独立API CLI的`--config`需要POSIX文件权限检查；Windows使用显式环境变量或桌面设置入口。

## 测试

使用安装好依赖的项目Python运行`qa/gates.py`。也可分项执行：

```sh
server/.venv/bin/python -m unittest discover -s server/tests -v
server/.venv/bin/python -m unittest discover -s desktop/tests -v
server/.venv/bin/python -m unittest discover -s deploy/tests -v
npm --prefix runtime/dsh test
npm --prefix web test
npm --prefix web run build
```

涉及真实桌面服务启动的测试需要先构建`web/dist`。批量资料库检查默认生成合成数据，不依赖外部教程；可通过`SHUYU_LIBRARY_SOURCE`指定符合目录格式的外部验收源。模型测试默认使用本机合成HTTP服务，不需要Key。

## 手机界面开发

手机断点为767px，底部导航依次为园区、对话、学习。监控、设备、任务和报告属于园区的下级功能；桌面保留完整工作台。`MobileGarden.vue`只展示父组件传入的园区事实，`KnowledgeLibrary.vue`的手机视图与桌面共享知识集合；对话始终复用同一份store、输入框和请求流程。

手机样式分别在`mobile-workbench.css`和`mobile-learning.css`。调整后除运行前端测试和构建，还应检查375、390、430及1440px布局；核对长消息、无数据、上传确认、阅读器、菜单关闭和园区切换。不要为贴合示意图写死监测值、模型回答或阅读进度；模拟来源与实际记录必须可以区分。桌面浏览器的尺寸模拟不能替代真机的软键盘、相机和麦克风验收。

手机“黄历与天气”复用`server/agriculture_calendar.py`的上海日期与既有历法库。`calendar.nodes`包含当天至366天后的节气和常见农历节日，倒计时按服务端民用日期计算；前端默认显示最近四条，可展开全部节点。固定农历节日不匹配闰月，除夕按次日春节判定；缺少历法库时明确显示不可用。提醒只在应用内展示，不创建通知任务；天气仍为演示样例。

聊天页的“新对话”直接复用现有 `createThread`，默认标题为“新对话”，无需先填名称；当前空对话会直接复用。创建期间锁定输入和引用编辑，同一账号、园区的成功返回才恢复未发送草稿与所选引用。详情读取失败仍保留草稿和错误，未知创建结果继续沿用原请求编号。手机输入框的加号展开六项工具，分别提供拍照/相册、录制语音、录音文件、上传资料、待办及设置；选中工具、切换页面或按 Escape 会收起。快捷问题仅写入草稿，不自动发送。聊天输入区上方的“本轮”入口显示当前技能与引用数量，分别进入既有设置与资料侧栏；图像或音频技能选中恰好一份对应媒体后可在无文字草稿时执行，其余引用不参加本次媒体处理；选中多份对应媒体或没有对应媒体时不可发送。

当前主链路依次为：园区事项直达、显式媒体分析或转写、确认待办、完成记录、阅读续问和 Markdown 报告。上传仅保存原件，普通文字对话不自动执行视觉分析。照片分析成功后，用户可以把已保存的分析正文放进可编辑草稿继续问；录音转写也需要核对后发送。媒体与下载的迟到响应必须同时检查账号、园区和对话归属。

任务完成使用独立的照片选择，不复用对话引用。阅读器“问问这篇”关闭阅读层、选中当前知识、清除旧文件引用并保留原有草稿，不自动发送。阅读器也支持对当前正文中的选段提问：只提取当前文档的选区、限制长度、写入草稿后由用户发送。报告先选择地块及任务范围，提交前再次与当前园区候选任务求交；空选不可生成，切换园区会清空选择。生成完成后查看报告，通过导出面板明确保存 Markdown。

界面仅提供 Markdown 导出，复用原 `exports` 接口的 `format: "md"` 和 `{asset}` 返回结构；原 docx/pptx 接口保留兼容。Markdown 包含事实、任务、记录、来源与照片说明，不嵌入原图或服务器鉴权 URL。导出生成和后续下载均检查报告来源及照片，来源撤销后拒绝服务端再下载；已下载到用户设备的文件无法追溯撤回。

## 模型与资料

通过设置页分别配置文字、图片、语音能力。常用环境字段：`SHUYU_PROVIDER_URL`、`SHUYU_PROVIDER_KEY`、`SHUYU_PROVIDER_MODEL`、`SHUYU_PROVIDER_CAPABILITIES`、`SHUYU_PROVIDER_VISION_MODEL`、`SHUYU_PROVIDER_ASR_MODEL`、`SHUYU_PROVIDER_ASR_ADAPTER`。支持的非思考模式可设`SHUYU_PROVIDER_THINKING=disabled`；需要reasoning_content的思考工具协议未实现。

文件可从知识库页面上传。批量资料导入使用`python -m server.library_import --help`；先dry-run核对，再显式apply。正文抽取、引用数量、媒体体积和模型调用有上限；不要通过删除校验来解决超限。

## 扩展和恢复

新增能力先定义输入、人工确认点及保存结果，再接入现有API与技能白名单。测试正常路径之外，还要覆盖越权、来源撤销、重复提交、取消和迟到响应。

SQLite使用WAL，运行中只复制主数据库文件可能丢数据。部署工具的backup/restore使用一致快照和原件核验。恢复到新目录并核对，不覆盖现有卷；schema升级后不要让旧代码直接写新库。

## 提交前测试版的配置升级

公开版统一使用 `SHUYU_*` 配置、`shuyu.*.v1` 技能标识、`shuyu_session` 会话 Cookie，以及 `shuyu-api.service` / `shuyu-worker.service`。首次安装按 README 初始化即可；这些标识不是旧测试版配置和待执行任务的自动迁移接口。

维护已有安装时，先在原版本完成或取消排队任务、关闭自动跟进；结果未知的外呼必须人工核对，不能通过重新排队重发。停止 API 和 worker，保存一致的数据与资产备份以及原代码、配置。在独立恢复目录验证后再切换，勿让新旧 worker 同时处理一个数据库。

按 `deploy/server.env.example` 更新配置键名，并显式设置 `SHUYU_DB` 与 `SHUYU_ASSET_ROOT` 指向经核对的数据副本；不要把新的默认数据库路径当成数据迁移。保持原有 secret、账号和数据归属，不要重新生成 seed 覆盖已有库。桌面私有 `local.json` 也需更新字段并保留权限；未知字段会拒绝加载，不能靠删掉配置绕过检查。

服务账号、环境文件、安装路径和 Nginx 模板需要成套核对；部署生成器使用 `shuyu.env`，默认示例路径为 `/opt/shuyu` 和 `/var/lib/shuyu`。会话 Cookie 改名后须重新登录。旧任务中冻结的技能策略和命令回执不得批量替换：当前版本未提供旧标识任务的续跑迁移；旧任务结果可供查看，但重新执行需重新确认。

回退时先停新服务，恢复配套的原代码、原配置和切换前一致备份；不要只回退代码后继续写已经变化的数据。以上流程本轮只用合成数据验证新安装，已有真实安装的迁移需单独验收。

向编程AI说明任务时，可使用：

> 阅读README、ARCHITECTURE、AGENTS和相关实现。先说明输入输出、数据归属和可能影响的功能，用合成数据复现，再做最小修复并补回归测试。保持既有账号、SQLite和turn执行边界，不放宽权限或自动重发未知外呼。报告改动文件、验证命令、passed/failed/not-run及剩余限制；涉及迁移时说明回退。

## 本机园区账号访问恢复

本机维护者可以恢复指定园区原持有账号的密码；这不会创建管理员角色或扩大账号权限。先停止服务并保存一致备份，确认园区ID与原持有用户ID，再执行：

```sh
server/.venv/bin/python -m server.app --config /absolute/private/local.json recover-owner-access --workspace WORKSPACE_ID --expected-user-id USER_ID
```

命令通过隐藏输入读取12至1024字符的新密码；自动化可用 `--password-stdin`，不得把密码作为命令参数。复用严格的私有配置校验。事务只更新目标账号密码并撤销其全部会话；用户名、业务数据和其他账号保持原样。目标不匹配或事务失败时全部回滚。恢复后用原用户名和新密码正常登录。回退应使用维护前的一致备份，不能将旧账号会话注入浏览器。
