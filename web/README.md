# 澍雨工作台前端

Vue 3、Pinia、Vite构建的农业生产与培训界面。通过同源`/api/v1`读取园区、知识、任务和对话，不在浏览器保存模型密钥。

## 开发

在项目根目录完成后端配置，使用Node.js 24：

```sh
npm --prefix web ci
npm --prefix web run dev
npm --prefix web test
npm --prefix web run build
```

开发入口为`http://127.0.0.1:5180`，API代理默认转向`http://127.0.0.1:6480`，可通过`VITE_DEV_API_TARGET`修改。后端`SHUYU_PUBLIC_ORIGIN`应与浏览器访问地址一致。构建输出`web/dist`，由本地启动器或部署服务提供；Vite preview不提供API服务。

## 组件与状态

`src/agriculture/AgricultureWorkbench.vue`组织六个业务入口及助手；`KnowledgeLibrary.vue`、`KnowledgeReader.vue`负责资料检索与阅读，`ReportDocument.vue`负责报告阅读，`LiveFieldPanel.vue`负责现场演示。手机布局在`responsive.css`。

登录使用HttpOnly cookie；写请求携带CSRF token。园区/账号/页面切换隔离迟到响应，同范围刷新不能丢失已提交操作的回执。模型命令使用固定编号，未知结果不能自动改号重发。文档正文和模型内容使用受限渲染，不执行任意HTML。

资料上传与发送给模型是不同操作。音频转写后先进入可编辑草稿。摄像头、机器人和监测样例必须保留模拟标识；接入真实设备前需要明确身份、时间戳与数据来源。

测试覆盖会话恢复、权限与CSRF协议、重复请求、并发刷新、资料引用、阅读安全、移动布局规则和媒体状态。运行时验证及端到端启动步骤见根目录开发指南。
