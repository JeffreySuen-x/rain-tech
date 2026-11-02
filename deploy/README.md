# 单节点部署与维护

运行边界是一个API、一个worker、本地持久SQLite和私有资产目录。代码目录只读，数据目录由服务用户拥有。当前不支持NFS或直接扩成多节点。

1. 安装Python3.11、Node24及锁定依赖，构建web。worker需要Node与runtime/dsh依赖，不能只上传前端。
2. 参考server.env.example配置实际域名、数据库、资产路径、随机secret及模型能力。配置文件不入Git，服务账号无特权。
3. 载入同一配置后，运行`server/.venv/bin/python -m server.app create-user your-account`，按提示设置密码；核对API与worker配置一致。参考 `shuyu-api.service` 和 `shuyu-worker.service`，两者读取同一份 `/etc/shuyu.env`；配置使用 `SHUYU_*`。确认 Node 在服务 PATH 中，示例服务账号 `shuyu` 拥有数据目录读写权限。
4. Nginx使用HTTPS同源代理，限制上传体积与请求速率；修改模板后执行nginx配置检查，再启用服务。
5. 验证登录、资料上传/阅读、模型工具调用、任务保存、报告导出、取消和重启后记录。设备和模型能力分别验收。

`python deploy/shuyu_release.py --help`提供本地pack、verify、backup、restore、status、preflight及render工具；不会自动安装服务、修改防火墙或调用模型。pack/backup包含运行数据，不是公开源码发布方式。

备份使用SQLite在线backup和原件hash清单。恢复到新目录，验证数据库、schema和资产后再切换；保留旧卷和配套代码。运行中的WAL数据库不能只复制主文件。未知外呼结果需要人工核对，不自动重发。

模板中的路径、账号、域名是部署示例；按实际环境配置。`README`中的回环开发模式不应直接作为公网服务。正式部署的TLS、权限、备份、限流和模型费用由部署方管理。
