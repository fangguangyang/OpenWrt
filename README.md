# OpenWrt

## 固件构建

默认基于官方 **ImmortalWrt 最新稳定版**，同时构建以下设备：

| 设备 | Target | Profile | 软件架构 |
| --- | --- | --- | --- |
| amd64 | `x86/64` | `generic` | `x86_64` |
| Widora MangoPi M28C（RK3528） | `rockchip/armv8` | `widora_mangopi-m28c` | 从官方 profile 读取 |

版本信息来自 [官方发布目录](https://downloads.immortalwrt.org/)。固件构建使用官方 APK ImageBuilder，以及 `fangguangyang/openwrt-dist` 发布的同版本签名软件源。ImageBuilder 文件名、架构和 SHA256 从官方元数据读取。

### GitHub 配置和启用顺序

1. 在 `openwrt-dist` 中完成所需版本、设备的软件源发布。对应 Release 已经完成时，直接复用，不需要再运行一次。
2. 在本仓库 `Settings → Secrets and variables → Actions` 中保留现有配置：
   - Secret **`TOKEN`**：可选，用于发布本仓库的固件 Release；只需本仓库 Contents 读写权限。未配置时使用工作流自带的 `github.token`。
   - 软件包签名私钥在 `openwrt-dist` 中配置，固件构建读取 Release 公钥。
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

- 软件清单位于 `profiles/common.packages` 和 `profiles/<设备>/packages`。首次启动配置、服务及热插拔脚本位于各 profile 的 `files/` 目录。
- 两种固件都使用 Argon、简体中文和上海时区。M28C 的 LAN 地址为 `192.168.60.1`，集成 AIC8800 Wi-Fi、PWM 风扇和 QModem。
- M28C Wi-Fi 默认启用，按实际 radio 的 band 命名为 `Widora_5G` / `Widora_2.4G`，密码为 `password123`；可在 `profiles/m28c/files/usr/sbin/m28c-wifi-defaults` 修改。支持驱动延迟加载，不假定存在两张 radio；初始化标记可防止后续开机覆盖手工 Wi-Fi 设置。
- amd64 保留 LAN `192.168.30.13` / 网关 `192.168.30.11`，使用 Argon 主题，默认安装 VMware 的 `open-vm-tools`。PVE/KVM 用户可在 `profiles/amd64/packages` 中将其替换为 `qemu-ga`；两者都安装 `/sbin/shutdown`，必须二选一。amd64 还配置了 ZTE 光猫每三小时校时，目标为 `192.168.1.1`。在路由器上把光猫的 Telnet 密码保存到 `/root/.zte-modem-password` 并将文件权限设为 `600`，任务才会连接光猫。
- 两种固件共用插件预设。SmartDNS 提供 6053 / 6553 两个端口以及 `smartdns-cn` / `smartdns-us` 上游组。AdGuardHome 在 7553 端口提供 DNS，预设上游和过滤列表，管理端口为 3000。OpenClash 提供 `SubConfig.yaml` 和配套 DNS 设置，导入实际订阅后即可配置节点。三项服务默认停用，基础 DHCP/DNS 使用 dnsmasq。
- 构建从 `scripts/prepare-openclash.py` 指定的上游 commit 下载对应架构的 OpenClash Meta 核心，校验归档 SHA256 和 ELF CPU 架构，记录在 `openclash-core.json`。更新核心时同时更新 commit 和两种架构的归档 SHA256。
- LAN、WAN、网桥和防火墙按设备配置。PPPoE、IPv6、root 密码和 SSH 公钥在对应设备的 LuCI 中设置。

### 可选功能

在 [amd64](profiles/amd64/features) 或 [M28C](profiles/m28c/features) 的 `features` 文件中，去掉所需功能行开头的 `#`。例如，在 amd64 的文件中启用 `statistics`，就只在 amd64 镜像里打包统计功能。本地构建和 GitHub Actions 都读取目标设备的文件。

| 功能 | 内容 |
| --- | --- |
| `passwall` | PassWall，订阅在 LuCI 中填写 |
| `statistics` | LuCI 统计及接口、传感器和中断采集 |
| `snmp` | SNMP 管理界面，启用前配置访问权限 |
| `upnp` | nftables 版 UPnP，服务默认停用 |
| `tools` | `dig`、`conntrack`、`nping`、Vim 等诊断工具 |
| `python` | Python 3 轻量运行时 |

### 在 M28C 上使用 FM350-GL

1. 将新固件写入 SD 卡，插好 SIM 卡和 FM350-GL 的 USB 转接板，再启动路由器。打开 `http://192.168.60.1`，进入 **调制解调器 → QModem → 概览**。QModem 扫描 USB 后显示型号、运营商、信号和连接状态。
2. 进入 **调制解调器 → QModem → 网络配置**，在 FM350-GL 那一行点击编辑。确认全局和模组的 **启用拨号** 都已勾选。APN 可以先选自动，无法连接时按 SIM 卡运营商选择，例如电信 `ctnet`、移动 `cmnet`、联通 `3gnet`。需要 PIN 的卡在同一处填写。保存并应用。
3. 回到 **概览** 查看拨号是否连通。收发短信在 **短信消息**，制式和频段设置在 **高级调制解调器配置**。重新拨号和拨号日志在 **网络配置** 的模组行。

FM350-GL 由 QModem 识别 USB ID `0e8d:7126` / `0e8d:7127` 并通过 AT + RNDIS 拨号。PDP 上下文索引留空即可采用当前 QModem 的 FM350-GL 默认值 `0`。[QModem 稳定版](https://github.com/FUjr/QModem/releases/tag/v3.3.0)

概览中没有模组时，进入 **QModem 设置** 确认 **启用 USB 扫描**，并检查转接板供电与 USB 数据线。概览能看到模组但没有连通时，先看 **网络配置 → 查看日志**，确认 SIM 已注册及 APN 正确。

### M28C SD 卡自动扩容

M28C 固定生成 **`ext4-sysupgrade.img.gz`** SD 镜像，初始根分区为 1 GiB。根文件系统使用官方 ImageBuilder 自带的 e2fsprogs 生成并进行完整检查，固定 ext4 特性和 inode 比例，避免原 `make_ext4fs` 镜像在大幅扩容后的元数据问题。解压写入整张 SD 卡后：

1. 首次启动按实际根文件系统确定 SD 设备，不写死 `mmcblk0`。检查机型、SD 类型、ext4、MBR，以及仅存在引导分区 1 和根分区 2。
2. 将根分区 2 的末端扩展到 SD 卡末尾，保留起点和引导区，自动重启一次，让内核重新读取分区表。
3. 再次启动使用内置 `resize2fs` 在线扩展 ext4，并用 `tune2fs` 验证容量。成功后记录标记，后续开机不再扩容或重启。

根目录 `/` 可使用卡上除引导区及文件系统开销之外的空间，无需另建 extroot。卡上若存在第三个分区，脚本会跳过扩容并记录日志，不覆盖该分区。扩分区或文件系统失败时不会写入成功标记，也不会不断自动重启。

首次启动请等待自动重启结束。可用 `df -h /`、`logread -e m28c-growroot` 验证扩容结果。ext4 镜像不具备 squashfs 只读系统层的恢复出厂方式，需要恢复纯净系统时重新写入 SD 卡。

软件源由 `openwrt-dist` 独立生成并作为 **GitHub Release 附件** 发布，tag 格式为 `packages-<发行版>-<版本>-<target>`，例如 `packages-immortalwrt-25.12.2-rockchip-armv8`，不带构建 ID 或执行轮次。同版本/target 重建会更新同一个 Release，签名私钥保留在软件源仓库，源 URL 和公钥保持不变。固件仓库读取已有地址和公钥并写入镜像；设备刷新软件列表即可获取同版本的新软件包。切换 OpenWrt 版本时再更换对应的 tag。官方源仍按官方发布路径使用。

APK 软件源地址为 `https://github.com/fangguangyang/openwrt-dist/releases/download/<tag>/packages.adb`。软件包签名和发布说明见 [openwrt-dist](https://github.com/fangguangyang/openwrt-dist)。

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
