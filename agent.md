# 项目定位：以 115 为核心，把云盘能力内建进 NAS-Tools

## 1. 当前目标共识

这套系统的目标已经明确：

- 下载在 `115`
- 主存储也在 `115`
- 本地不承担正式媒体库存储
- 本地更多承担控制、缓存、代理、接口职责
- `alist` 只作为参考实现，不作为最终部署组件
- 最终必须对外暴露一个稳定目录，或者一个可挂载到本地的稳定路径，供 `Emby/Jellyfin` 等媒体应用使用

因此最终形态不是：

- `nas-tools + alist + 115`

而是：

- `nas-tools(吸纳 115 挂载/访问/云端文件管理能力) + 115`

换句话说，我们要做的是把原本由 `alist` 提供的一部分“115 文件系统抽象能力”内化进 `nas-tools`。

## 2. 两个项目对我们的价值分别是什么

### 2.1 `nas-tools` 的价值

`nas-tools v2.9.2` 的核心身份，其实不是单纯“找资源和下资源”，而是“围绕影音对象做自动化整理”。

它已经把下面这些能力串成了一条完整链路：

- 订阅
- 搜索
- 下载器抽象
- 媒体识别
- 资源筛选
- 下载后的归类与重命名
- 媒体库存在性判断
- 定时任务
- Web 管理后台
- API
- 媒体服务器集成

尤其要注意的是：

- `Searcher` 不是只返回搜索结果，它会直接调用 `Downloader`
- `Downloader` 不只是下发下载，它还负责检查媒体是否已存在、下载后如何进入后续流程
- `FileTransfer` 不是边缘模块，它承担了媒体识别、命名规范、目录组织、字幕处理、媒体库刷新
- `MediaServer` 不只是展示层，它参与“缺哪些集、是否已存在、刷新哪个库”的判断

所以更准确的说法是：

`nas-tools` 本来就是一个“自动整理型”的影音编排系统。

我们后续不是要给它加上“整理能力”，而是要把它原本偏本地的整理模型，改造成偏 115 云端的整理模型。

### 2.2 `alist` 的价值

`alist` 对我们最重要的价值不是“拿来部署”，而是“拿来抄能力模型”。

目前确认可借鉴的核心点有：

- 115 云盘驱动设计
- 115 Open 驱动设计
- 目录浏览、移动、复制、删除、重命名抽象
- 离线任务抽象
- 下载链接获取逻辑
- WebDAV 服务实现
- 统一驱动接口和路径抽象

也就是说，`alist` 是参考信息源，是实现样本，不是最终运行时依赖。

## 3. 新的产品形态

最终产品应该是一个“云盘中心型 NAS-Tools”：

1. 用户在 `nas-tools` 中添加订阅或发起搜索
2. `nas-tools` 把资源投递到 `115` 离线
3. 文件保存到 `115` 的业务目录
4. `nas-tools` 直接管理 115 中的目录、文件和归档结构
5. `nas-tools` 对外提供统一访问入口或稳定挂载路径
6. 媒体服务器或播放器通过这个目录/路径访问远程内容

这个过程中，`nas-tools` 的主任务仍然是“整理”：

- 把资源整理成稳定的影视目录结构
- 把电影和剧集整理成媒体应用可识别的路径
- 维护媒体应用视角下的持续稳定性

变化的只是整理发生的位置：

- 以前默认整理到本地媒体库
- 以后要整理到 115 视角下的稳定远程目录，或者整理成对外暴露的稳定虚拟目录

这里的关键变化是：

- 不再依赖本地目录作为正式媒体库
- 不再依赖外部 `alist` 作为 115 文件系统代理
- 由 `nas-tools` 自己承担远程路径和远程文件能力

## 3.2 把原版目录模型翻译成 115 版本

原版 `nas-tools` 的落地方式，其实可以概括成三层：

- 下载目录
- link 目录
- 媒体库目录

它的核心思想不是“目录多”，而是“把下载态和媒体消费态分开”。

原版语义大致是：

1. 下载器先把文件放进下载目录
2. `nas-tools` 再把文件整理到一个稳定的 link 目录视图
3. `Emby/Jellyfin/Plex` 扫描这个稳定目录

我们未来的 115 方案，也应该保留这个三层思想，只是把它换成远程语义：

- `115 下载目录`
- `115 归档目录`
- `媒体应用可见目录/挂载路径`

更具体地说：

### 第一层：115 下载目录

这层对应原版“下载目录”。

作用：

- 承接 115 离线任务的原始落点
- 允许目录结构暂时不规范
- 作为任务完成后的待整理输入区

特点：

- 面向下载任务
- 不直接给媒体应用扫描
- 可以混乱，但必须可追踪

### 第二层：115 归档目录

这层是未来最重要的一层，对应原版的“link 目录”语义。

作用：

- 按电影/剧集规则归类
- 形成稳定命名
- 形成稳定季/集结构
- 作为媒体视图的权威组织层

特点：

- 这层应该由 `nas-tools` 主导维护
- 这里的目录结构要尽量稳定
- 这层才是真正意义上的“整理完成结果”

### 第三层：媒体应用可见目录或挂载路径

这层对应原版“媒体库目录”。

作用：

- 暴露给 `Emby/Jellyfin`
- 让媒体应用看到一个可长期扫描的稳定目录视图
- 尽量屏蔽 115 内部原始结构和任务态目录

这层在实现上可以有不同形式：

- 一个由 `nas-tools` 暴露出来的本地可挂载路径
- 一个虚拟文件系统目录
- 一个 WebDAV 挂载后的本地路径
- 一个经过本地映射生成的稳定目录视图

但对媒体应用来说，效果应尽量一致：

- 看起来像普通目录
- 路径长期稳定
- 不因为下载任务的中间态而频繁变化

## 3.3 新模型下的关键原则

这三层里，最关键的是第二层。

因为真正决定系统质量的，不是：

- 能不能把任务丢给 115

而是：

- 能不能把 115 里的文件整理成稳定的归档目录

所以后续真正的主战场仍然是“整理层”，只是整理对象从本地文件变成了 115 内的远程文件。

## 3.1 对媒体应用的直接目标

这套系统最终不是只要“能下载、能整理”就够了，而是必须满足媒体应用的接入要求。

也就是说，最终我们要交付的是下面两种能力中的至少一种：

- 方案 A：`nas-tools` 暴露一个媒体应用可直接扫描的目录
- 方案 B：`nas-tools` 提供一个能挂载到本地的稳定路径，挂载后再交给 `Emby/Jellyfin`

无论采用哪种方案，对媒体应用来说都应尽量表现成：

- 路径稳定
- 目录结构稳定
- 剧集更新后路径不频繁变化
- 可以长期作为媒体库根目录使用

## 4. 对 NAS-Tools 现有模块的重新定位

### 4.1 保留并强化

- `app/subscribe.py`
  继续做订阅编排中心

- `app/searcher.py`
  继续做资源搜索与筛选中心

- `app/downloader/`
  继续做下载入口，但要升级为 115 优先

- `app/media/`
  继续做媒体识别、元数据、TMDB/豆瓣/Bangumi 能力

- `web/`
  继续做控制台、API 和任务可视化

### 4.2 重点改造

- `app/downloader/client/client115.py`
  当前只是一个简化版 115 下载器，能力太薄，需要升级

- `app/downloader/client/_py115.py`
  当前只覆盖了部分 115 接口，后续要扩展成更完整的 115 能力层

- `app/filetransfer.py`
  当前它其实已经是项目的整理核心，但默认目标是本地媒体库。
  后续不是弱化它，而是要把它升级为“云端归档和远程路径管理核心”。

- `app/sync.py`
  当前更像“本地目录变化驱动的整理入口”，后续要从“文件事件驱动”转向“远程状态驱动”

- `app/mediaserver/`
  当前假设媒体库偏本地路径，后续要适配远程路径、远程流或 `.strm`

## 5. 我们要从 AList 吸纳什么

我建议把要借鉴的能力拆成四类。

### 5.1 115 文件系统抽象

目标是在 `nas-tools` 内形成统一的 115 文件能力接口，包括：

- 列目录
- 获取文件信息
- 创建目录
- 移动文件
- 复制文件
- 删除文件
- 重命名
- 获取下载链接
- 上传

这部分可以参考 `alist` 的 115 驱动接口设计。

### 5.2 115 离线任务抽象

除了现在已有的简化离线能力，后续要补齐：

- 离线任务列表
- 任务状态标准化
- 任务删除
- 批量下发
- 目标目录控制
- 失败原因透出

这部分可以参考 `alist` 中 `OfflineList`、`OfflineDownload`、`DeleteOfflineTasks` 的抽象方式。

### 5.3 远程路径与对象模型

后续 `nas-tools` 里要引入比现在更清晰的远程对象模型：

- 115 目录对象
- 115 文件对象
- 远程路径
- 业务归档路径
- 对外暴露路径

不能再把核心逻辑建立在“本地文件路径”上。

这几个路径概念，最好和上面的三层目录一一对应：

- 下载态路径
- 归档态路径
- 暴露态路径

### 5.4 WebDAV/远程访问能力

如果后续需要给媒体服务器提供统一访问入口，可以把 `alist` 的 WebDAV 设计思路吸纳进来：

- 认证
- 路径解析
- 权限控制
- 远程对象到 WebDAV 资源的映射

这不代表一定要完整照搬 `alist` 的 WebDAV 代码，但它的设计思路很值得参考。

另外，它也提示了我们一个很现实的方向：

- `nas-tools` 可以内建一个“媒体专用访问层”
- 这个访问层最终要么提供 WebDAV，要么提供本地可挂载路径，要么提供能生成稳定目录视图的虚拟文件系统

## 6. 后续架构原则

### 原则 1：115 是唯一权威存储

文件真实状态以 115 为准。
本地缓存目录不是权威数据源。

### 原则 2：NAS-Tools 内建远程文件能力

最终不依赖 `alist` 进程。
115 文件系统相关能力要由 `nas-tools` 自己提供。

### 原则 3：从“本地搬运”转向“云端归档”

后续重点不是：

- 下载完成后把文件移动到本地媒体库

而是：

- 下载完成后把文件在 115 内归档到正确目录
- 维护稳定的远程路径
- 对外暴露统一访问方式

这里要特别强调：

“归档”不是新增需求，而是 `nas-tools` 的原有核心职责。

我们真正要做的是把原有这套：

- 识别
- 分类
- 命名
- 入库
- 刷新媒体库

从本地文件系统语义迁移到 115/远程目录语义。

这里的“入库”，后续更准确地理解为：

- 把文件放入 115 中的稳定归档目录
- 并把这个归档目录映射成媒体应用可见目录

### 原则 4：减少对本地文件事件的依赖

原有 `sync.py` 偏向目录变化监听。
但在云端优先架构里，更可靠的是：

- 定时轮询
- 任务状态机
- 云端目录扫描
- 远程对象差异同步

### 原则 5：本地只保留短生命周期能力

本地允许有：

- 缓存
- 海报与元数据缓存
- 上传/校验临时文件
- 调试日志
- 可选的转码或中转缓存

本地不应默认保留完整影音资产。

## 7. 代码层面我建议新增的能力域

为了让改造更清晰，建议后续在 `nas-tools` 内逐步形成几个新的能力域。

### 7.1 `115 文件服务层`

负责：

- 文件与目录操作
- 下载链接生成
- 远程对象查询
- 路径抽象

这层应当成为 `filetransfer.py`、下载器、Web 访问能力的共同基础。

### 7.2 `115 任务服务层`

负责：

- 离线下载任务
- 状态追踪
- 任务重试
- 任务归档

### 7.3 `远程媒体归档层`

负责：

- 在 115 内部完成电影/剧集目录归档
- 远程改名
- 季/集结构管理
- 剧集增量更新处理

### 7.4 `远程访问层`

负责：

- 对外文件访问接口
- 可选 WebDAV
- 可选流式访问
- 媒体服务器集成所需的路径或链接暴露

## 8. 我对第一批改造工作的判断

最先要做的，不是直接抄 `alist` 一大段代码进来，而是先把改造边界划好。

建议按这个顺序推进：

1. 明确 `client115` 和未来“115 文件服务层”的边界
2. 明确哪些 `filetransfer.py` 逻辑必须从本地路径改成远程路径
3. 明确媒体服务器最终消费什么
4. 再决定是否要内建 WebDAV，还是先走直链/`.strm`

其中第 2 点其实是整件事的核心，因为这项目真正的主轴就是整理链路，而不是下载链路。

更具体地说，第 2 点要拆成三件事：

1. 哪些逻辑属于“下载态目录”
2. 哪些逻辑属于“归档态目录”
3. 哪些逻辑属于“媒体应用暴露目录”

这里第 3 点现在已经更具体了：

- 我们最终必须让 `Emby/Jellyfin` 消费一个目录式入口
- 不管这个入口底层来自虚拟目录、挂载路径还是 WebDAV 映射，对媒体应用都应该尽量看起来像“正常文件目录”

## 9. 现阶段最重要的判断

目前最关键的认知转变是：

我们不是“集成一个 115 下载器”。

我们是在把 `nas-tools` 从一个偏本地媒体库工具，重构成一个：

“以 115 为下载和存储中心，内建远程文件系统能力的云端优先影音管理系统。”

同时也不是重做一套新的产品骨架。

更准确地说，我们是在保留 `nas-tools` 作为“自动整理引擎”的前提下，把它的整理对象从本地文件切换成 115 中的远程文件与远程目录。

## 10. 下一步建议

接下来最值得做的是：

1. 梳理 `nas-tools` 当前配置里和 115、路径、媒体服务器相关的配置项
2. 产出一版“需要从 AList 吸纳的能力清单”
3. 把“下载目录 -> link 目录 -> 媒体库目录”翻译成 115 版配置模型
4. 增加一版“媒体应用接入方案比较”
5. 列出 `nas-tools` 第一批必须改的文件和模块
6. 再开始正式落第一阶段代码

## 11. 当前结论

最终方向应当是：

- 继续以 `nas-tools` 为主工程
- 把 `alist` 当作 115 云盘实现参考
- 将关键实现吸纳进 `nas-tools`
- 让 `nas-tools` 自己具备远程文件、远程归档、远程访问能力
## 12. 路线修正：暂不走 115 OpenAPI 主链

现阶段决定：

- `115 OpenAPI` 不作为主实现路线
- `115 session/cookie` 继续作为默认且唯一推荐的运行路径
- 代码中保留 `open provider`，但只作为研究占位和接口映射样本

原因：

- 真实账号和应用下的 OpenAPI 权限并不稳定
- 文档可见不代表接口可长期稳定调用
- 当前项目最关键的目录管理、离线下载、任务轮询、任务删除和后续整理链路，在 `session/cookie` 路线上已经有真实联调基础
- 对现阶段项目来说，优先保证可用性和可维护性，比继续投入 OpenAPI 更重要

后续原则：

- 默认只围绕 `session` 路径继续增强
- `open` 代码保留注释和结构，方便未来重新评估
- 不再把 OpenAPI 作为近期里程碑或主战场

## 13. Session 路线下一步能力边界

既然近期主链确定为 `session/cookie`，后续实现应当优先补齐这几类能力：

- 离线任务能力：创建任务、查询任务、删除任务
- 目录能力：列目录、查目录、创建目录、递归确保目录存在
- 文件归档能力：移动文件、重命名文件、删除文件
- 媒体整理能力：把已完成任务从 staging 目录整理到 library 目录

当前第一批已经落到 115 client 的 session 能力包括：

- `ensure_dir(path)`
- `getdirid(path)`
- `getiddir(file_id)`
- `listdir(cid)`
- `addtask_urls(content, download_dir)`
- `gettasklist(page)`
- `deltask(info_hash)`
- `move(file_ids, to_dir_id)`
- `rename(file_id, new_name)`
- `delete(file_ids)`

这些能力先作为底层远程文件操作接口存在。下一阶段再把它们接入更高层的远程归档逻辑，避免直接把 `filetransfer.py` 里大量本地路径假设一次性改散。

## 14. 测试脚本边界

`tests/test_115_client.py` 是当前 115 session 客户端的独立持久化测试入口。

它会把测试状态写入：

- `config/temp/115_client_test.json`

它会把每次响应快照写入：

- `config/temp/115_client_test_responses/`

当前保留的主要命令：

- `qrcode-create`
- `qrcode-status`
- `qrcode-exchange`
- `cookie-login`
- `listdir`
- `listdir-path`
- `getdirid`
- `ensure-dir`
- `gettasklist`
- `gettask`
- `wait-task`
- `addtask`
- `move`
- `rename`
- `delete`

注意：

- `move`、`rename`、`delete` 默认都是 dry-run，只有显式传 `--execute` 才会修改 115 远端文件。
- `alist-open-auth-device-code` 和 `alist-open-get-token` 现在保留为 disabled research command，不再真的请求 AList/OpenAPI。
- 后续真实联调远端文件移动或删除前，必须先确认目标 `file_id` 和目标目录，避免误动媒体库内容。

## 15. nas-tools 媒体文件操作覆盖评估

当前 `nas-tools` 中真正涉及媒体文件操作的核心集中在：

- `app/filetransfer.py`
- `app/utils/system_utils.py`
- `app/utils/path_utils.py`
- `app/media/scraper.py`
- `app/subtitle.py`
- `app/sync.py`
- `app/downloader/downloader.py`

已被 115 session client 底层覆盖的能力：

- 查询目录：`listdir`
- 路径转目录 ID：`getdirid`
- 文件/目录 ID 转路径：`getiddir`
- 创建目录：`ensure_dir`
- 离线任务创建：`addtask`
- 离线任务查询：`gettasklist`
- 离线任务删除：`deltask`
- 远端移动：`move`
- 远端重命名：`rename`
- 远端删除：`delete`

尚未完整覆盖的 `nas-tools` 媒体文件语义：

- 本地文件扫描：`os.walk`、`os.listdir`、`os.path.exists`、`os.path.isdir`、`os.path.isfile`
- 文件大小判断：`os.path.getsize`
- 硬链接/软链接：`os.link`、`os.symlink`
- 复制：`shutil.copy2`
- 目录复制/蓝光原盘整目录处理
- 覆盖旧文件：先删除旧文件再转移新文件
- 字幕关联转移：按同目录同名字幕查找并复制
- 刮削文件写入：NFO、poster、fanart、thumb 等小文件落盘
- 字幕下载：下载 zip、解压、复制字幕到媒体目录
- 文件系统事件监听：`watchdog` 监控本地目录变化
- 目标媒体库存在性判断：按目录结构扫描是否已有电影/剧集
- 收藏移动：Emby/Jellyfin 点红星后把电影目录移动到精选分类

替代方向：

- 不要直接让 `filetransfer.py` 操作 115 API；应新增远程文件系统适配层，例如 `Pan115RemoteFS`。
- `copy/link/softlink` 在 115 中不应一比一复刻；第一阶段统一降级为远端 `move + rename`，保持单份文件。
- 如果需要“非破坏性整理”，后续再补 115 copy API；在此之前不要把 copy/link 映射成真实复制。
- `os.walk/listdir/exists/getsize` 应替换为远程目录树查询和远程文件元数据查询。
- NFO、poster、字幕这类小文件不能只写本地缓存；如果媒体库直接读 115 暴露目录，就必须支持上传小文件到 115 对应目录。
- `watchdog` 本地目录监听不适合纯 115；应由离线任务轮询、目录轮询或 115 事件能力替代。
- 媒体库刷新仍可沿用现有 Emby/Jellyfin/Plex API，因为它不关心底层文件来自哪里，只要媒体应用能看到最终目录。

阶段判断：

- 当前不是“都覆盖到了”。
- 当前覆盖的是 115 session 底层原语。
- 下一阶段应做远程整理层，把 `filetransfer.py` 的“本地文件系统操作语义”翻译成“115 远端文件系统操作语义”。

## 16. Pan115RemoteFS 第一版

已经新增 `app/downloader/client/pan115_remote_fs.py`，目标是作为 `filetransfer.py` 和 115 API 之间的中间层。

第一版能力：

- `normalize_path(path)`
- `dirname(path)`
- `basename(path)`
- `ensure_dir(path)`
- `listdir(path)`
- `listdir_id(cid)`
- `stat(path)`
- `exists(path)`
- `isdir(path)`
- `isfile(path)`
- `getsize(path)`
- `walk(path, max_depth=None)`
- `move_id(file_ids, target_dir)`
- `rename_id(file_id, new_name)`
- `delete_id(file_ids)`
- `move_path(source_path, target_path, execute=False)`
- `delete_path(path, execute=False)`

设计原则：

- 高层代码只面对“远程路径”和“标准化 item”，不要直接碰 115 原始字段。
- `move_path`、`delete_path` 默认 dry-run，先返回计划，不直接修改 115。
- 第一阶段不实现 `copy/link/softlink`，避免制造看起来成功但语义不真实的整理结果。
- `copy/link/softlink` 后续如果要支持，应明确新增远端 copy 或虚拟索引语义，不能偷偷映射成移动。

已经验证：

- `remote-list --path /影音库/downloads/movies --limit 5 --show-items`
- `remote-stat --path /影音库/downloads/movies/ABF-345`

以上都是只读测试，均成功并已写入 `config/temp/115_client_test_responses/`。

## 17. 远程整理 Planner 第一版

已经新增 `app/downloader/client/pan115_transfer_planner.py`。

定位：

- 这是 `filetransfer.py` 迁移到 115 远端整理前的 dry-run 规划层。
- 第一版不直接导入 `FileTransfer` 或 `MetaInfo`，避免拉起完整媒体依赖。
- 调用方需要显式传入媒体元数据，例如 `media_type/title/year/season/episode/videoFormat`。

当前能力：

- 根据 `media.movie_name_format` 生成电影目标路径。
- 根据 `media.tv_name_format` 生成电视剧/动漫目标路径。
- 扫描 115 远端源目录，过滤媒体文件后生成移动计划。
- 使用 `media.min_filesize` 过滤小文件，例如广告视频。
- 输出 `RemoteFS.move_path` dry-run 计划。

已验证：

- 对 `/影音库/downloads/movies/ABF-345` 执行 `remote-walk`，发现一个 7.89GB 主视频和一个 2MB 广告视频。
- `remote-plan` 已能过滤广告视频，只为主视频生成计划。
- 生成目标示例：`/影音库/library/movies/ABF-345 (2026)/ABF-345 (2026) - 1080p.mp4`

安全修正：

- 初版 `RemoteFS.move_path(..., execute=False)` 曾为了拿目标目录 ID 调用 `ensure_dir`，导致 dry-run 也会创建目录。
- 现已修复：dry-run 只调用 `getdirid` 做只读探测，不创建目录。
- dry-run 对不存在目标目录会返回 `target_dir_exists=false` 和 `target_dir_would_create=true`。

已知现场影响：

- 修复前的一次 dry-run 已创建空目录：`/影音库/library/movies/ABF-345 (2026)`。
- 不应擅自删除该目录，后续如需清理应由用户确认后执行。

后续补充：

- `RemoteFS.move_path` 已增加目标存在性检测。
- 默认不覆盖目标文件；如果 `target_exists=true` 且未显式 `overwrite`，计划会失败并返回 `target already exists`。
- 只有显式传 `overwrite` 时，执行阶段才允许先删除旧目标再移动。
- `RemoteFS.normalize_path` 会把 115 返回的 `/根目录/...` 统一归一化为业务路径 `/...`。
- 测试脚本新增 `remote-plan-task`，可通过 115 离线任务 `info_hash` 推导源路径并生成整理计划。

已验证：

- `remote-plan-task --info-hash 2d7cc2a2bfc7b387a6cfdddd65a3258b353e929f ...`
- 能从任务推导源目录 `/影音库/downloads/movies/ABF-345`
- 能过滤广告小文件，只为主视频生成目标移动计划

## 18. 115 配置、API 与 WebDAV 第一版

本轮目标是让前端和接口层能直接面向 115 远端文件系统。

配置层：

- `client115` 新增远端目录配置：
- `remote_download_path`
- `remote_movie_path`
- `remote_tv_path`
- `remote_anime_path`
- `webdav_enabled`
- `webdav_root`
- `webdav_user`
- `webdav_password`
- `webdav_readonly`

API 层：

- 新增 `/api/v1/pan115/config`
- 新增 `/api/v1/pan115/stat`
- 新增 `/api/v1/pan115/list`
- 新增 `/api/v1/pan115/mkdir`
- 新增 `/api/v1/pan115/move`
- 新增 `/api/v1/pan115/delete`
- 新增 `/api/v1/pan115/plan`

这些接口统一走 `Pan115RemoteFS` 和 `Pan115TransferPlanner`，避免前端直接接触 115 原始字段。

WebDAV 层：

- 新增 Flask blueprint：`web/pan115_webdav.py`
- 注册路径：`/dav/115`
- 支持 `OPTIONS`
- 支持 `PROPFIND`
- 支持 `HEAD/GET` 目录浏览
- 支持文件 `HEAD/GET` 通过 115 下载直链 302 跳转
- 支持 `MKCOL`
- 支持 `DELETE`
- 支持 `MOVE`
- `PUT` 暂未实现，返回 501

安全策略：

- WebDAV 默认关闭。
- WebDAV 默认只读。
- 配置了 `webdav_user` 或 `webdav_password` 后启用 Basic Auth。
- 写操作受 `webdav_readonly` 控制。

下载直链：

- 已参考 AList `drivers/115` 和本地 `115driver` / `115drive-webdav` module cache。
- `_py115.py` 已移植 `pick_code -> proapi.115.com/app/chrome/downurl` 的 RSA/XOR 编码链路。
- 调用链路为 `_py115.py -> Pan115SessionProvider -> Pan115RemoteFS -> WebDAV GET`。
- WebDAV 文件访问当前采用 302 跳转到 115 临时下载链接，先不做本地代理流式转发，避免本地承担大文件流量。
- 测试脚本新增 `remote-download-url`，会把临时 URL 脱敏后持久化响应；需要完整 URL 时显式传 `--show-url`。

重要边界：

- 当前 WebDAV 已能让客户端挂载、浏览 115 目录，并把文件读取交给 115 临时链接。
- 写操作仍默认只读，需要显式关闭 `webdav_readonly`。
- `PUT` 暂未实现；后续如果要支持媒体应用写入，需要补 115 上传/秒传链路。

已验证：

- 使用 `C:\Users\xjh1996\AppData\Local\Programs\Python\Python310\python.exe -m py_compile` 检查新增/修改文件，语法通过。
- `remote-download-url --path /影音库/downloads/movies/ABF-345/hhd800.com@ABF-345.mp4 --user-agent "Mozilla/5.0 115Browser/23.9.3.2"` 成功解析 115 临时下载链接。
- 下载直链测试响应已持久化到 `config/temp/115_client_test_responses/latest_115_remote_download_url.json`，默认隐藏完整 URL。

## 19. 115 前端配置工作台

已在下载器设置页的 `client115` 弹窗中新增“115 远端工作台”。

位置：

- `web/templates/setting/downloader.html`

当前能力：

- `client115` 不再只依赖通用平铺表单，已改为 115 专属配置面板。
- 认证配置按 `Provider / 认证方式 / Session / QRCode / OpenAPI Research` 分组。
- `auth_type` 已补入配置 schema，可在前端选择 `cookie/qrcode/open`。
- 远端目录配置按下载根、电影库、剧集库、动漫库分组展示。
- WebDAV 配置按启用开关、只读开关、根目录、用户名、密码分组展示。
- 保存前会为常用远端目录补默认值，降低空配置误用。
- Provider/Auth/WebDAV 会触发前端显隐联动。
- 自动展示当前服务的 WebDAV 地址：`/dav/115/`
- 支持复制 WebDAV 地址。
- 支持从配置项快速切换目录：
- `webdav_root`
- `remote_download_path`
- `remote_movie_path`
- `remote_tv_path`
- 支持输入任意 115 远端路径并调用 `/api/v1/pan115/list` 浏览。
- 支持调用 `/api/v1/pan115/stat` 测试路径是否可访问。
- 目录项可点击下钻。

设计原则：

- 前端只面对标准化远端路径，不接触 115 原始 `fid/cid/pc` 字段。
- 这个工作台贴在配置弹窗里，用于降低“盲填路径”的成本。
- 暂不在前端暴露下载直链，避免临时 URL 泄露到页面日志或复制链路。
- `input_select_GetVal` 已支持 `textarea`，用于保存长 Cookie 和二维码会话 JSON。
