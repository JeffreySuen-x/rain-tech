# 澍雨服务端

Flask API、SQLite和Python worker提供园区、对话、资料、任务与报告服务。安装与本地体验见[根README](../README.md)，模块职责见[架构说明](../ARCHITECTURE.md)。

API和worker使用相同的数据库、资产目录、secret及Origin。独立运行分别使用`python -m server.app serve`和`python -m server.app worker`；新账号通过`python -m server.app create-user USERNAME`交互创建，或使用桌面设置入口。

默认监听回环6480；生产使用HTTPS同源反向代理，不直接暴露开发HTTP服务。媒体能力按提供商配置开启。资料原件不作为静态资源公开，读取和工具调用均校验账号、园区及来源。

模型HTTP设置单次绝对时限并受本轮剩余预算与取消控制；已派发未知调用不自动重试。schema未知版本拒绝启动。备份、恢复和部署见[部署说明](../deploy/README.md)。
