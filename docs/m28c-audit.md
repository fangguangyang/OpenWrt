# M28C + FM350-GL / SD 卡检查记录

检查日期：2026-11-19。对应 ImmortalWrt 25.12.2、`rockchip/armv8`、`aarch64_generic`、内核 6.12.103。使用官方 ImageBuilder 和已经发布的匹配软件源完成本地构建；未操作真实设备。

## 检查结论

原配置能安装拨号组件，但没有自动创建蜂窝接口和关联插件端口；新版流程未接入旧 `resize` 模块，SD 根分区固定为 1 GiB。仅按原配置刷机不能满足自动识别模组和使用整张 SD 卡空间的目标。

本次已补齐自动识别和 SD 扩容。新建 `cellular` 接口时默认填写中国电信 APN `ctnet`，PIN、认证信息保持空白；保留刷机后的手工修改，后续检测及重新插拔不会覆盖已保存的 APN。

| 项目 | 发现和处理 |
| --- | --- |
| 实际依赖安装 | 使用官方 ImageBuilder 完成 320 个包的安装，包含默认设备包和递归依赖；无依赖或文件冲突 |
| FM350 驱动 | 官方 `option` 模块的 USB 设备表包含 `0e8d:7126` / `0e8d:7127`；保留 RNDIS、CDC、串口、QMI/MBIM 相关驱动 |
| 自动识别 | 按 USB ID、接口号及驱动绑定识别实际 AT 端口和数据网卡，支持串口重新编号及快速拔插后的 USB 枚举变化 |
| 拨号初始化 | 自动创建 XMM 协议的 `cellular`；默认 IPv4、metric 20；加入原 WAN 防火墙区域，沿用 NAT 和 LAN → WAN 转发 |
| 信号、短信、锁频 | 为 3ginfo-lite、SMS Tool、Modemband 写入检测到的端口；保留已经手工选择的其他端口 |
| 上游 XMM 脚本 | 修正 FM350 数据网卡发现逻辑对固定 MAC 和 sysfs 目录深度的依赖；构建时校验上游脚本结构，变化时要求重新审查 |
| Wi-Fi 初始化 | 保留官方 AIC8800 默认依赖；支持驱动延迟加载；已初始化的 AP 后续不覆盖手工设置 |
| SD 镜像类型 | M28C 只生成可直接挂载并扩展的 ext4；没有将 squashfs/F2FS 可写层误交给 `resize2fs` |
| 根分区扩展 | 识别实际启动 SD 卡，检查只有分区 1、2，保持起点和引导区，将分区 2 扩至卡尾；自动重启一次 |
| 已挂载分区 | GNU Parted 的 `--script` 模式不能确认正在使用的分区；改为受控提供确认，再独立读取分区表核验结果 |
| 文件系统生成 | 实测原 `make_ext4fs` 根镜像存在 bitmap padding 异常，大幅扩容后出现 resize inode 大小异常；M28C 改用 ImageBuilder 自带 e2fsprogs 生成，并在封装前运行完整检查 |
| 文件系统扩展 | 重启读取新分区大小后运行 `resize2fs`，再检查 ext4 块数；成功才记录标记，后续开机跳过 |
| OpenClash 核心 | 按目标 CPU 从固定上游 commit 直接下载并内置 Meta 核心，校验归档 SHA256 和 ELF 架构，记录来源与哈希 |
| DNS/代理启动 | OpenClash、AdGuardHome、MosDNS、SmartDNS 默认停用；保留 dnsmasq 的基础 DHCP/DNS，等配置订阅或 DNS 规则后再启用 |
| LAN 地址 | 实际 profile 为 `192.168.60.1`，修正文档之前写成参考仓库 `192.168.6.1` 的不一致 |

## 验证证据

- `python3 -m unittest discover -s tests -v`：26 项通过，包括两个 USB ID、ttyUSB/ttyACM 目录差异、串口编号变化、额外数据分区、失败重试、禁止反复重启、已挂载分区确认、CPU 架构和归档内容校验。
- profile 中的 shell 脚本通过 BusyBox ash 语法检查；构建脚本通过 Bash 语法检查。
- 官方 ImageBuilder 实际安装 320 个包并生成 ext4 SD 固件，校验信息保存在 `image/m28c/`。
- 构造 32 GiB 稀疏 SD 镜像，通过真实 GNU Parted 验证：模拟根分区正在使用时，旧 `--script` 调用失败；受控确认方式成功，引导分区和根分区起点保持不变，末端达到最后一个扇区。
- 将生成的 ext4 根文件系统复制并扩大到 32 GiB SD 卡扣除引导区后的大小，使用真实 `resize2fs` 扩容；扩容前、后的 `e2fsck -fn` 全部通过。
- 从最终压缩镜像读取分区表并校验根分区内容与已检查的 ext4 文件一致；检查镜像内脚本、服务链接、权限、核心架构和软件包清单。
- ARM64、amd64 两种 OpenClash 核心均实际下载并通过架构校验；本次完整固件构建验证针对 M28C。

原始包清单：`image/m28c/package-manifest.txt`。核心来源：`image/m28c/openclash-core.json`。最终镜像核验：`image/m28c/validation.json`。以上均为本地生成物，不进入 Git。

## 刷机后预期

1. 把 `*-widora_mangopi-m28c-ext4-sysupgrade.img.gz` 解压写入整张 SD 卡，插回 M28C；首次启动等待自动扩分区和一次重启结束。
2. 访问 `http://192.168.60.1`。Wi-Fi 名称按实际频段为 `Widora_5G` 或 `Widora_2.4G`，密码 `password123`。
3. USB 模组识别后，“网络 → 接口”出现 `cellular`，协议 **Intel XMM Cellular**，APN 已预填中国电信 `ctnet` 并自动连接。实际 SIM 卡如需其他 APN 或 PIN，可在此修改并保存应用。
4. 用 `df -h /` 验证空间，`logread -e m28c-growroot` 查看扩容日志；用 `logread -e fm350-detect`、`ifstatus cellular` 查看识别和拨号状态。

SD 卡上除引导区、对齐空隙及 ext4 元数据之外的空间都会进入根分区。存在第三个分区时自动扩容会跳过，以保留该分区。ext4 没有 squashfs 只读系统层的恢复出厂方式，需要回到纯净系统时重写 SD 卡。

真实 M28C 的上电、Wi-Fi 发射、USB 转接板供电、SIM 注册和运营商数据连接仍需刷机后验证；本记录中的模拟和镜像检查不代表已经完成硬件实测。

## 上游依据

- [M28C 官方设备定义](https://github.com/immortalwrt/immortalwrt/blob/openwrt-25.12/target/linux/rockchip/image/armv8.mk)
- [modemfeed FM350/XMM 协议](https://github.com/koshev-msk/modemfeed/blob/master/packages/net/xmm-modem/root/lib/netifd/proto/xmm.sh)
- [modemfeed AT 端口匹配](https://github.com/koshev-msk/modemfeed/blob/master/luci/protocols/luci-proto-xmm/root/usr/libexec/rpcd/luci.proto.xmm)
- [GNU Parted 3.6 源码](https://ftp.gnu.org/gnu/parted/parted-3.6.tar.xz)，`parted/parted.c` 和 `parted/ui.c` 的已挂载分区及脚本模式处理。
