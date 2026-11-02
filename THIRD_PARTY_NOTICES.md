# 第三方依赖与素材

项目自有代码使用根目录MIT许可证。下列依赖通过其公开接口使用，各自保留原作者版权和许可证；项目许可证不替代依赖许可证。安装或分发依赖、二进制程序时，须一并保留其发行包中的完整声明。

| 组件 | 主要依赖与许可证 | 完整版本/声明 |
| --- | --- | --- |
| 前端 | Vue、Pinia、Vite、Vitest（MIT） | `web/package-lock.json`、`deploy/THIRD_PARTY_WEB_NOTICE.txt` |
| Agent运行时 | DeepSeek Harness、Cordis、Zod（MIT） | `runtime/dsh/package-lock.json`、`runtime/dsh/NOTICE.md` |
| HTTP与服务 | Flask、Werkzeug、Jinja2、MarkupSafe、ItsDangerous、Click、Blinker、Gunicorn（BSD/MIT） | `server/requirements-lock.txt`及安装包许可证 |
| 文档 | python-docx、python-pptx（MIT），pypdf、lxml（BSD-3-Clause），XlsxWriter（BSD-2-Clause） | `server/AGRICULTURE_SOURCES.json`及安装包许可证 |
| 图片 | Pillow（MIT-CMU）及其二进制发行中的编解码组件 | `server/NOTICE.Pillow-13.0.0.txt` |
| 历法 | lunar_python（MIT） | `server/NOTICE.lunar_python-1.4.8.txt` |
| Python辅助 | typing_extensions（PSF-2.0）、packaging（Apache-2.0或BSD-2-Clause） | 安装包许可证 |

源码参考链接：[DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)、[Vue](https://github.com/vuejs/core)、[Flask](https://github.com/pallets/flask)、[pypdf](https://github.com/py-pdf/pypdf)、[Pillow](https://github.com/python-pillow/Pillow)、[lunar_python](https://github.com/6tail/lunar-python)。锁文件列出完整依赖树，表格只列主要组件。

蓝色水滴、界面插画及示例葡萄园图片是本项目生成的视觉素材，随项目提供。`examples/student-demo/images/ORIGIN.json`保存两张场景插画的校验值；它们不是真实现场照片或病害诊断证据。手机巡检背景为生成的虚构葡萄园示意，来源、用途与校验值记录在 `web/public/friendly/ORIGIN.json`；巡检路线与状态由应用绘制。六篇葡萄资料是本项目编写的学习笔记，引用的外部资料仅作为阅读来源，不代表外部站点内容以本项目MIT许可证授权。用户另行导入资料时，应确认其使用权限。
