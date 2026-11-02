# 架构说明

```text
Vue工作台 → Flask API → SQLite / 资料原件目录
                 ↓
             turns任务表 → Python worker → Node DSH AgentLoop
                                          ├─ 工具回调 → Python领域函数
                                          └─ 模型回调 → 有限时的Python传输进程
```

网页负责交互，API负责账号和资源权限；SQLite保存业务事实与任务回执。DSH负责Agent循环，Python负责模型调用、工具副作用、预算及结果发布。本机启动器管理设置、数据目录和服务生命周期，服务器部署复用相同业务模块。

|目录/模块|职责|
|---|---|
|web/src/agriculture|园区、对话、知识阅读器、报告与模拟现场界面|
|web/src/store.js|账号、园区、对话及请求归属状态|
|server/app.py|会话、CSRF、园区/对话API、turn队列与worker入口|
|server/agriculture.py|资料、任务、记录、设备、学习与跟进业务|
|server/agriculture_materials.py|有界文档解析、媒体处理和Office输出|
|server/agriculture_reports.py|报告事实快照、来源及图片有效性检查|
|server/agent_runtime.py|执行预算、持久回执、取消和进程通信|
|server/agent_provider.py|兼容模型HTTP传输，拒绝重定向和隐式代理|
|server/skill.py|技能版本、指令与工具白名单|
|runtime/dsh|使用DSH公开接口的Agent循环适配器|
|desktop|本地账号设置、配置与服务生命周期|
|server/student_demo.py、examples/student-demo|可重新生成的合成样例|
|deploy|单节点部署模板与备份恢复工具|

## 需要保持的边界

`users/sessions`管理账号会话；`workspaces`是园区；`threads`组织对话；`turns`是唯一业务执行队列。农业对象在`agriculture_entities`中保存。所有跨资源引用必须校验owner和workspace，不能仅根据客户端传来的ID访问数据。

一次模型/工具调用先持久化dispatched状态，结果确定且任务仍有效时封存为sealed。已发出但结果未知的请求不得自动重发，以免重复费用或副作用。取消、来源撤销、代次和租约校验阻止迟到结果发布。模型传输进程是每次调用的资源隔离，不是第二个任务队列。

报告和引用保留事实快照与来源摘要。原件变动、撤销或越权不能被显示层绕开。设备模拟与真实设备上报必须保留不同来源和时间。

当前为单节点、本地磁盘、一个API和一个worker。增加学校角色或多节点时，需设计账号归属、迁移、并发租约、文件存储和费用承担，不能只增加worker数量或替换登录页。
