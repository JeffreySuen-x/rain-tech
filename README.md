# 澍雨科技 · Rain-tech

澍雨是一个面向农业生产与培训的 Agent 工作台，把知识学习、现场问答、园区观察、任务执行与生产记录放在同一个界面中。当前以葡萄园为演示场景，帮助使用者查资料、理解现场情况、完成任务并回顾过程，也为农业教学、科研实践和后续应用开发提供可运行的基础。

## 能做什么

- **对话与技能**：根据选定资料回答问题，通过工具查询园区记录和任务；支持配置文字、图像与语音模型。
- **学习知识库**：导入文档、检索正文、阅读原文、选择引用并记录学习反馈。
- **任务与记录**：直接打开具体农事任务，填写完成情况并独立选择现场照片，生成事实简报并导出 Markdown。
- **园区工作台**：查看地块、监测记录、设备状态与提醒。
- **手机黄历**：查看农历、节气与传统宜忌；提示近期节气和农历节日，可展开未来一年日期与倒计时。提醒展示在园区页面内。
- **手机界面**：底部依次为“园区、对话、学习”。园区优先展示待办，监控、设备、任务和报告始终归园区；照片或录音上传后，明确选择分析或转写，再编辑草稿继续问。阅读器可以带着本篇原文进入对话。
- **可体验的样例**：提供葡萄园、六篇基础资料、示例任务和插画；摄像头、机器人、天气及动态监测均为模拟展示。

AI回答依赖你配置的模型服务。没有模型配置时，可以使用本地资料阅读、园区、任务和报告功能；AI请求会明确提示未配置。样例不代表真实设备接入或农艺诊断能力。

## 本地启动

需要 Python 3.11、Node.js 24 和 npm。以下命令在仓库根目录执行，适用于macOS/Linux：

```sh
python3.11 -m venv server/.venv
server/.venv/bin/python -m pip install -r server/requirements-lock.txt
npm --prefix runtime/dsh ci --ignore-scripts
npm --prefix web ci
npm --prefix web run build
server/.venv/bin/python -m server.student_demo --output seed

SHUYU_BUNDLE_ROOT="$PWD" SHUYU_DATA_DIR="$PWD/.local-data" \
  server/.venv/bin/python desktop/shuyu_desktop.py
```

浏览器将打开首次设置页。创建自己的本机账号，模型配置可以稍后补充。服务默认使用 `http://127.0.0.1:5196`。端口已被其他程序占用时，可另设 `SHUYU_PORT`。

`seed` 是样例初始化输入，只生成一次；已存在时生成器会拒绝覆盖。后续启动只需最后一条命令。你的实际数据保存在 `.local-data`，不能用seed替换已有用户数据。

再次设置模型或停止服务，在同一启动命令末尾加 `--setup` 或 `--stop`。关闭网页不会停止后台服务。Windows PowerShell用法见[开发指南](DEVELOPING.md)；Windows完整运行验收仍待完成。

## 模型配置

在首次设置页或 `--setup` 页面填写HTTPS基地址、模型名及API Key，按实际服务能力勾选文字、图片和语音。文本使用兼容的Chat Completions与工具调用协议；图片需要支持image_url；语音需要支持transcriptions或input_audio适配器。不同提供商需要分别验收，不能仅凭“兼容”标识保证所有功能可用。

资料上传先保存在本地服务；模型问答或媒体处理时，对应输入会发送给所配置的模型服务。凭据留在后端配置中，不放前端或Git。硬件、正式教学与生产使用应由领域人员核验结果。

## 开发与部署

- [架构说明](ARCHITECTURE.md)：组件职责、数据归属、Agent执行流程。
- [开发指南](DEVELOPING.md)：热更新、测试、资料导入、扩展与故障排查。
- [贡献指南](CONTRIBUTING.md)：如何提交问题和改动。
- [AI工作约定](AGENTS.md)：让编程助手理解项目边界。
- [AI开发交接](AI_HANDOFF.md)：接手顺序、现有行为与验收基线。
- [部署说明](deploy/README.md)：单节点API、worker、SQLite与Nginx配置。
- [运行边界](SECURITY.md)：资料处理、模型请求与对外部署的限制。

现有账号、权限和单机运维可作为参考实现，开发者可以继续设计组织、班级、角色和设备接口。改变这些边界时需要同时设计数据迁移与访问控制测试。

运行检查：

```sh
server/.venv/bin/python qa/gates.py
```

默认面向单节点、本地持久磁盘、一个API和一个worker。多节点运行、真实硬件与各模型服务需另行验收。后端配置统一使用 `SHUYU_*`；从提交前测试版升级时，先阅读[配置升级说明](DEVELOPING.md#提交前测试版的配置升级)。

## 许可证

项目自有代码采用 [MIT](LICENSE)，Copyright (c) 2026 jeffrey。第三方依赖及其许可证见 [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES.md)。
