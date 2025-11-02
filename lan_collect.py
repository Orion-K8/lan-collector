# tools/lan_fingerprint_collect.py
import subprocess, re, ipaddress, json, os, sys

def _run(cmd):
    return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL, shell=True)

def get_active_ipv4_and_mask_windows():
    out = _run('ipconfig')
    blocks = re.split(r'\r?\n\r?\n', out)
    for b in blocks:
        ipm = re.search(r'IPv4 地址[^\:]*:\s*([\d\.]+)', b) or re.search(r'IPv4 Address[^\:]*:\s*([\d\.]+)', b)
        nm  = re.search(r'子网掩码[^\:]*:\s*([\d\.]+)', b) or re.search(r'Subnet Mask[^\:]*:\s*([\d\.]+)', b)
        gw  = re.search(r'默认网关[^\:]*:\s*([\d\.]+)', b) or re.search(r'Default Gateway[^\:]*:\s*([\d\.]+)', b)
        if ipm and nm and gw and re.match(r'\d+\.\d+\.\d+\.\d+', gw.group(1)):
            return ipm.group(1), nm.group(1), gw.group(1)
    raise RuntimeError("未找到活动IPv4接口（请确认已连接到目标局域网）")

def get_active_ipv4_and_mask_posix():
    # Linux/macOS：从默认路由取网关，再从ip/ifconfig解析本机IP与掩码
    try:
        route = _run('ip route get 1.1.1.1')
        m = re.search(r'src\s+([\d\.]+)', route)
        gwm = re.search(r'via\s+([\d\.]+)', route)
        if not m or not gwm:
            raise RuntimeError
        ip = m.group(1); gw = gwm.group(1)

        ifcfg = _run('ip -o -f inet addr')
        nm = None
        for line in ifcfg.splitlines():
            if ip in line:
                m2 = re.search(r'inet\s+([\d\.]+)/(\d+)', line)
                if m2:
                    mask_bits = int(m2.group(2))
                    nm = str(ipaddress.IPv4Network(f'0.0.0.0/{mask_bits}').netmask)
                    break
        if not nm:
            raise RuntimeError
        return ip, nm, gw
    except Exception:
        raise RuntimeError("未能自动解析网络（支持 Windows/Linux/macOS；Linux需具备 ip/arp 命令）")

def get_active_ipv4_and_mask():
    if os.name == 'nt':
        return get_active_ipv4_and_mask_windows()
    return get_active_ipv4_and_mask_posix()

def get_mac_of_ip(ip):
    try: _run(f'ping -n 1 {ip}' if os.name=='nt' else f'ping -c 1 {ip}')
    except: pass
    out = _run('arp -a' if os.name=='nt' else 'arp -n')
    for line in out.splitlines():
        if ip in line:
            m = re.search(r'([0-9a-f]{2}([-:])){5}[0-9a-f]{2}', line, re.I)
            if m: return m.group(0).upper().replace(':','-')
    raise RuntimeError(f"未找到网关 {ip} 的MAC（请确保已连接并有通信）")

def calc_cidr(ip, mask):
    net = ipaddress.IPv4Network(f"{ip}/{mask}", strict=False)
    return str(net)

if __name__ == "__main__":
    try:
        ip, mask, gw_ip = get_active_ipv4_and_mask()
        gw_mac = get_mac_of_ip(gw_ip)
        cidr = calc_cidr(ip, mask)

        info = {
            "subnets": [cidr],
            "gateways": [{"ip": gw_ip, "mac": gw_mac}]
        }
        print(json.dumps(info, ensure_ascii=False, indent=2))
        with open("lan_info.json", "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False, indent=2)
        print("\n已保存到 lan_info.json ，请把该文件发回给供应商签发许可。")
    except Exception as e:
        print("采集失败：", e)
        sys.exit(1)
