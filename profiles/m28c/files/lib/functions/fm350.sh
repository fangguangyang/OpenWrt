#!/bin/sh
# USB interface numbers match modemfeed's luci.proto.xmm port discovery.
# Walk sysfs instead of depending on ttyUSB numbering or an Ethernet MAC.
fm350_for_port() {
    local path iface vid pid candidate driver
    FM350_PORT= FM350_NET= FM350_USB=
    path=$(readlink -f "/sys/class/tty/${1##*/}/device") || return 1
    while [ "$path" != / ] && [ -n "$path" ]; do
        [ -f "$path/bInterfaceNumber" ] && break
        path=${path%/*}
    done
    [ -f "$path/bInterfaceNumber" ] || return 1
    iface=$(cat "$path/bInterfaceNumber")
    FM350_USB=${path%/*}
    [ -f "$FM350_USB/idVendor" ] && [ -f "$FM350_USB/idProduct" ] || return 1
    vid=$(cat "$FM350_USB/idVendor")
    pid=$(cat "$FM350_USB/idProduct")
    case "$vid:$pid:$iface" in
        0e8d:7126:04|0e8d:7127:06) ;;
        *) return 1 ;;
    esac
    FM350_PORT=$1
    for candidate in "$FM350_USB"/*/net/*; do
        [ -d "$candidate" ] || continue
        driver=$(readlink -f "$candidate/device/driver")
        case "${driver##*/}" in
            rndis_host|cdc_ncm|cdc_ether)
                # More than one data interface is ambiguous; do not guess.
                [ -z "$FM350_NET" ] || return 1
                FM350_NET=${candidate##*/}
                ;;
        esac
    done
    [ -n "$FM350_NET" ]
}

fm350_find() {
    local entry
    for entry in /sys/class/tty/ttyUSB* /sys/class/tty/ttyACM*; do
        [ -e "$entry/device" ] || continue
        fm350_for_port "/dev/${entry##*/}" && return 0
    done
    return 1
}
