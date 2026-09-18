#
# windows-server-2022-core.pkrvars.hcl
#
# Packer variables for the Windows Server 2022 Server Core template.
# This is the headless operating-system base for SQL Server and similar
# service workloads. Administrative consoles remain on a management host.
#
# Maintainer: HybridOps.Tech
# Organization: HybridOps.Tech
#

name        = "windows-server-2022-core-template"
description = "Windows Server 2022 Server Core Evaluation - Proxmox Template"

iso_file     = "windows-server-2022-eval.iso"
iso_url      = "https://go.microsoft.com/fwlink/p/?LinkID=2195280"
iso_checksum = "sha256:3e4fa6d8507b554856fc9ca6079cc402df11a8b79344871669f0251535255325"

os   = "win10"
bios = "seabios"

cpu_type    = "host"
cpu_cores   = 4
memory      = 8192
disk_size   = "60G"
disk_format = "raw"

communicator = "winrm"

# SERVERDATACENTERCORE selects Server Core from the Windows Server media.
windows_edition        = "Windows Server 2022 SERVERDATACENTERCORE"
windows_language       = "en-US"
windows_input_language = "en-US"

# Cloudbase-Init consumes the Proxmox config-drive on clones so Windows can
# apply per-interface DHCP/IPAM intent. The platform VM module enables delivery
# only when windows_config_drive=true.
cloudbase_init_enabled = true
cloudbase_init_msi_url = "https://www.cloudbase.it/downloads/CloudbaseInitSetup_Stable_x64.msi"

additional_iso_files = [
  {
    iso_file     = "virtio-win-0.1.285.iso"
    iso_url      = "https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/archive-virtio/virtio-win-0.1.285-1/virtio-win-0.1.285.iso"
    iso_checksum = "sha256:e14cf2b94492c3e925f0070ba7fdfedeb2048c91eea9c5a5afb30232a3976331"
  }
]

unattended_content = {
  "/Autounattend.xml" = {
    template = "http/Autounattend-server.xml.pkrtpl"
    vars = {
      driver_version = "2k22"
    }
  }
}
