# OpenWrt

## 自动构建（当前流程）

默认基于官方 **ImmortalWrt 最新稳定版**，同时构建以下设备：

| 设备 | Target | Profile | 软件架构 |
| --- | --- | --- | --- |
| amd64 | `x86/64` | `generic` | `x86_64` |
| Widora MangoPi M28C（RK3528） | `rockchip/armv8` | `widora_mangopi-m28c` | 从官方 profile 读取 |

版本信息来自 [官方发布目录](https://downloads.immortalwrt.org/)。固件构建直接复用 `fangguangyang/openwrt-dist` **已经发布的软件源**，再使用同版本的官方 ImageBuilder 打包镜像。固件工作流不会调用或重跑软件源流水线。ImageBuilder 文件名、压缩格式、架构和 SHA256 均自动读取，旧版 opkg 和新版 apk 根据官方元数据自动切换。

### GitHub 配置和启用顺序

1. 在 `openwrt-dist` 中完成所需版本、设备的软件源发布。对应 Release 已经完成时，直接复用，不需要再运行一次。
2. 在本仓库 `Settings → Secrets and variables → Actions` 中保留现有配置：
   - Secret **`TOKEN`**：可选，用于发布本仓库的固件 Release；只需本仓库 Contents 读写权限。未配置时使用工作流自带的 `github.token`。
   - 软件包签名私钥只在 `openwrt-dist` 中配置，本仓库读取已发布公钥，不再使用 `APK_SIGNING_KEY` / `OPKG_SIGNING_KEY`。
   - Variable **`OPENWRT_VERSION`**：推荐 `latest`；也支持 `25.12.2`、`25.12`、`openwrt-25.12`、`SNAPSHOT`。固定版本必须存在于所选发行版的官方目录。
3. 推送本仓库改动，或进入 Actions → **Firmware** 手动运行。手动输入版本可覆盖仓库变量。

无需把 TOKEN 或版本写入代码。每次 push、每周六北京时间 04:00 及手动运行会启动构建。两种镜像全部成功后发布一个新的 Release；每种设备另有完整 artifact，包含镜像、校验文件和构建元数据。

可选 Variables：

| 名称 | 默认值 | 用途 |
| --- | --- | --- |
| `OPENWRT_DISTRO` | `immortalwrt` | 可改为 `openwrt`；M28C 要求 ImmortalWrt 有对应 profile |
| `OPENWRT_DEVICES` | `amd64,m28c` | 设备列表；选择官方 OpenWrt 时使用 `amd64` |
| `PACKAGE_REPOSITORY` | `fangguangyang/openwrt-dist` | 已发布软件源所在的公开 GitHub 仓库 |

准备阶段根据发行版、版本和 target 定位固定 tag，校验软件源的 `build.json`、架构、包格式、版本代码及 SDK SHA256，并检查索引和公钥存在。缺少匹配的发布物时明确报错，不自动触发编译、不混用其他版本。`latest` 指官方最新稳定版；如果该版本的软件源尚未发布，可先在 `openwrt-dist` 中发布，或明确选择已有软件源的固件版本。

### 固件定制

- 公共软件：`profiles/common.packages`；设备软件：`profiles/<设备>/packages`。这些是新版 CI 使用的列表。
- 首次启动配置：`profiles/common/files/` 和 `profiles/<设备>/files/`，包括 `etc/uci-defaults/`、启动服务及热插拔脚本。
- M28C 参考 `Widora-M28C-Build`，集成 QMI/MBIM、Modemband、SMS Tool、PWM 风扇、iStore 和 QuickStart。LAN 地址为 `192.168.60.1`，LuCI 和 amd64 一样默认使用 Argon 主题。保留官方设备 profile 的 AIC8800 SDIO/Wi-Fi 驱动默认项。
- M28C 集成 FM350 USB 的 RNDIS/CDC、串口驱动、`xmm-modem`、`luci-proto-xmm` 和 `luci-app-3ginfo-lite`。拨号组件采用 [modemfeed 当前包名](https://github.com/koshev-msk/modemfeed/tree/master/packages/net/xmm-modem)，对应旧教程里的 `fm350-modem` / `luci-proto-fm350`。自动配置流程见下文。
- M28C Wi-Fi 默认启用，按实际 radio 的 band 命名为 `Widora_5G` / `Widora_2.4G`，密码为 `password123`；可在 `profiles/m28c/files/usr/sbin/m28c-wifi-defaults` 修改。支持驱动延迟加载，不假定存在两张 radio；初始化标记可防止后续开机覆盖手工 Wi-Fi 设置。
- amd64 保留 LAN `192.168.30.13` / 网关 `192.168.30.11`，使用 Argon 主题，默认安装 VMware 的 `open-vm-tools`。PVE/KVM 用户可在 `profiles/amd64/packages` 中将其替换为 `qemu-ga`；两者都安装 `/sbin/shutdown`，必须二选一。
- OpenClash、AdGuardHome、MosDNS 使用对应架构的软件。构建从 `scripts/prepare-openclash.py` 指定的上游 commit 直接下载 OpenClash Meta 核心，校验归档 SHA256 和 ELF CPU 架构，记录在 `openclash-core.json`。更新核心时同时更新 commit 和两种架构的归档 SHA256。代理订阅与附加 DNS 服务默认停用，基础 DHCP/DNS 使用 dnsmasq。可在 LuCI 中配置后启用相应服务。

### M28C + FM350-GL（USB 转接）

刷入 SD 卡并接好模组后，`fm350-detect` 服务每 10 秒检查 USB 枚举，匹配 `0e8d:7126` 的接口 `04`、`0e8d:7127` 的接口 `06`。这些接口号与 [上游端口识别逻辑](https://github.com/koshev-msk/modemfeed/blob/master/luci/protocols/luci-proto-xmm/root/usr/libexec/rpcd/luci.proto.xmm) 一致，不写死 `/dev/ttyUSB2` / `/dev/ttyUSB4`。数据网卡从同一个 USB 设备的驱动绑定信息获取，不依赖固定网卡名或 MAC。

- 自动创建 `cellular` 接口，协议为 **Intel XMM Cellular**，默认 IPv4、自动连接、路由 metric 为 20，并加入现有 `wan` 防火墙区域，使用系统原有 NAT 和 LAN → WAN 转发。
- 自动为 3ginfo-lite、Modemband 和 SMS Tool 设置实际 AT 端口，支持开机延迟枚举及拔插后串口重新编号。已手工选择的其他端口会保留。
- 新建蜂窝接口时默认填写中国电信 APN `ctnet`，PIN、认证账号保持空白。可进入 `http://192.168.60.1` → 网络 → 接口 → `cellular` 修改；后续检测及重新插拔不会覆盖已保存的 APN。
- 不同时运行 ModemManager 等第二套拨号管理服务。QMI/MBIM 组件为其他 USB 模组保留，FM350 默认使用 XMM/AT 协议。
- 如需完全手工维护，可设置 `uci set fm350.main.enabled=0; uci commit fm350; /etc/init.d/fm350-detect stop`。

### M28C SD 卡自动扩容

M28C 固定生成 **`ext4-sysupgrade.img.gz`** SD 镜像，初始根分区为 1 GiB。根文件系统使用官方 ImageBuilder 自带的 e2fsprogs 生成并进行完整检查，固定 ext4 特性和 inode 比例，避免原 `make_ext4fs` 镜像在大幅扩容后的元数据问题。解压写入整张 SD 卡后：

1. 首次启动按实际根文件系统确定 SD 设备，不写死 `mmcblk0`。检查机型、SD 类型、ext4、MBR，以及仅存在引导分区 1 和根分区 2。
2. 将根分区 2 的末端扩展到 SD 卡末尾，保留起点和引导区，自动重启一次，让内核重新读取分区表。
3. 再次启动使用内置 `resize2fs` 在线扩展 ext4，并用 `tune2fs` 验证容量。成功后记录标记，后续开机不再扩容或重启。

根目录 `/` 可使用卡上除引导区及文件系统开销之外的空间，无需另建 extroot。卡上若存在第三个分区，脚本会跳过扩容并记录日志，不覆盖该分区。扩分区或文件系统失败时不会写入成功标记，也不会不断自动重启。

首次启动请等待自动重启结束。可用 `df -h /`、`logread -e m28c-growroot` 验证结果；`logread -e fm350-detect`、`ifstatus cellular` 查看模组识别及接口状态。ext4 镜像不具备 squashfs 只读系统层的恢复出厂方式，需要恢复纯净系统时重新写入 SD 卡。

不再移植旧的全量 `.config`、无条件替换 Go 的第三方分支或删除 MosDNS 安装项。软件源中 MosDNS 核心和 UI 使用同一来源，避免两个包争用启动脚本。

软件源由 `openwrt-dist` 独立生成并作为 **GitHub Release 附件** 发布，tag 格式为 `packages-<发行版>-<版本>-<target>`，例如 `packages-immortalwrt-25.12.2-rockchip-armv8`，不带构建 ID 或执行轮次。同版本/target 重建会更新同一个 Release，签名私钥保留在软件源仓库，源 URL 和公钥保持不变。固件仓库读取已有地址和公钥并写入镜像；设备刷新软件列表即可获取同版本的新软件包。切换 OpenWrt 版本时再更换对应的 tag。官方源仍按官方发布路径使用。

apk 的源地址为 `https://github.com/fangguangyang/openwrt-dist/releases/download/<tag>/packages.adb`；opkg 的 `src/gz` 使用相同地址去掉 `/packages.adb` 的基础目录。详细手工配置见 [openwrt-dist](https://github.com/fangguangyang/openwrt-dist)。原 Git 分支/raw 软件源地址需手动迁移。

### 本地检查和构建

```bash
python3 -m unittest discover -s tests -v
python3 scripts/release.py resolve --version latest --output release.json
python3 scripts/release.py feeds --metadata release.json --output package-feeds.json
```

准备好 `openwrt-dist` 发布的 Release 软件源后，从 `release.json` 的 `include` 取出一个设备对象，保存为 `/tmp/build.json`，再运行：

```bash
bash scripts/build-image.sh /tmp/build.json 'https://github.com/fangguangyang/openwrt-dist/releases/download/<tag>'
```

本地使用 Linux/Python 3.11+ 及 ImageBuilder 的构建依赖。构建 amd64 时也需要 `qemu-utils` 和 `genisoimage`，用于生成虚拟磁盘和 ISO。GitHub Actions 会自动安装这些依赖。

## 旧版 Docker / modules 使用方式

以下是保留的旧版入口；新版 CI 使用上面的 `profiles` 和 `scripts/build-image.sh`，不读取旧 `.env` 或 `custom_env.sh`。旧 modules 中的第三方 opkg 源适用于旧版系统；新版 apk 构建请使用当前流程。

一个可以简单自定义 OpenWrt 固件的工具

## 关于此项目

通常在官方下载的固件会缺少一些软件包，且在初次启动时需要配置拨号账号密码等，官方提供的 [Firmware Selector](https://firmware-selector.openwrt.org/)，不能添加自定义软件源，此项目就是为了解决这些问题，以减少新系统启动时必须的初始化配置为目的，达到开机无需配置即可使用

另外项目会将配置持久化，相比 Firmware Selector，无需每次生成固件都需要重新配置

- 基于 [ImageBuilder](https://openwrt.org/docs/guide-user/additional-software/imagebuilder) 构建，几分钟即可构建完成
- 使用 [Docker](https://www.docker.com/) 运行 ImageBuilder，无需安装额外的软件和依赖

## 特性

- 集成常用代理软件及其最佳实践配置，如 OpenClash, daed, passwall
- 可配置默认 LAN 口 IP，PPPoE 账号密码，推荐的 IPv6 配置，刷机完成后，无需配置网络
- 模块化，更易维护

<!-- Prerequisites -->
## 准备

安装 Docker https://docs.docker.com/engine/install/

## 安装和配置

```bash
git clone https://github.com/ekkog/OpenWrt.git
cd OpenWrt
```

项目配置通过 .env 文件进行，您可以通过修改 .env 文件来配置项目

.env 中可以配置两类变量，一类是 ImageBuilder 的环境变量，一类是项目的环境变量

`CONFIG_` 开头的变量是 ImageBuilder 的环境变量，运行时会将这些变量传递给 ImageBuilder，您可以通过 ImageBuilder 的文档来了解这些变量的含义

`MODULES` 是项目的环境变量，用于配置项目使用的 modules，后面会详细介绍

## 使用

```bash
❯ ./run.sh --help                                                                           
--image: specify imagebuilder docker image, find it in https://hub.docker.com/r/openwrt/imagebuilder/tags or https://hub.docker.com/r/immortalwrt/imagebuilder/tags
--profile: specify profile
--with-pull: pull image before build
--rm-first: remove container before build
--use-mirror: use mirror
-h|--help: print this help
```

示例

```bash
./run.sh --image=immortalwrt/imagebuilder:rockchip-armv8-openwrt-23.05.1 --profile=friendlyarm_nanopi-r2s --rm-first --with-pull --use-mirror=1                                  
```

## modules

本项目所有的特性均通过 modules 进行配置，您可以根据自己的需求，自由选择需要的模块，或者自行添加新的模块

每个 module 都是一个目录，目录名即为 module 名，目录下包含以下文件

```bash
packages #一个文本文件，定义本 module 依赖的软件包, 空格分隔
files/ #定义本 module 需要的文件，按照 [OpenWrt 的 files](https://openwrt.org/docs/guide-developer/toolchain/use-buildsystem#custom_files) 规范，放置到对应的目录下，最后会将所有 module 的 files 合并到 files 目录下
post-files.sh #定义本 module 的预处理脚本，会在将当前 module 的 files 合并到最终目录后执行
.env #定义本 module 的环境变量，会将其中的变量的值替换到 files/uci-defaults/ 目录下的文件中
```

如果您想在项目根目录的 .env 中统一定义变量，以便在 module 中使用，可以在根目录的 .env 中设置 `USE_SYTEM_ENV=1`，这样在 module 中就可以使用系统环境变量了

您可以通过在项目根目录下的 .env 中定义 MODULES 变量，来选择需要的 module，例如

```bash
MODULES="python -tools"
```

以减号开头的 module 会被排除，上面的例子中，会增加 python module，并排除 tools module

内置 modules https://github.com/EkkoG/OpenWrt/tree/master/modules

默认使用的 modules 参见 https://github.com/EkkoG/OpenWrt/blob/master/build.sh

## 更多

请查看 [Wiki](https://github.com/EkkoG/OpenWrt/wiki)

## 致谢

感谢以下项目，使得我的上网体验又有所提升

- [OpenWrt](https://openwrt.org/)
- [ImmortalWrt](http://immortalwrt.org/)
- [clash](https://github.com/Dreamacro/clash)
- [OpenClash](https://github.com/vernesong/OpenClash)
- [Clash.Meta](https://github.com/MetaCubeX/Clash.Meta)
- [dae](https://github.com/daeuniverse/dae)
