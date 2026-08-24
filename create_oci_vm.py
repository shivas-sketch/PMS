#!/usr/bin/env python3
"""Create an Oracle Cloud VM for the PMS project with auto-retry on capacity errors.

Prerequisites:
  1. OCI CLI installed and configured (oci setup config)
  2. API public key uploaded to OCI Console
  3. SSH key for VM access generated (~/.ssh/pms-vm-key)

Usage:
  python3 create_oci_vm.py

The script auto-discovers compartment, subnet, and Ubuntu image,
then retries VM creation across all availability domains until it succeeds.
"""

import json
import os
import subprocess
import sys
import time

# ── Configuration ──────────────────────────────────────────────────────────
CONFIG_FILE = os.path.expanduser("~/.oci/config")
SSH_PUB_KEY = os.path.expanduser("~/.ssh/pms-vm-key.pub")
VM_NAME = "pms-server"
SHAPE = "VM.Standard.A1.Flex"
OCPUS = 4
MEMORY_GB = 24
BOOT_VOLUME_GB = 50
RETRY_INTERVAL_SEC = 30
MAX_RETRIES = 120  # 1 hour max

OCI = ["oci", "--config-file", CONFIG_FILE]


def run_oci(args, check=True):
    """Run an OCI CLI command and return parsed JSON output."""
    cmd = OCI + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        if check:
            print(f"ERROR: {' '.join(cmd)}")
            print(f"stderr: {result.stderr}")
            return None
        return None
    try:
        return json.loads(result.stdout) if result.stdout.strip() else {}
    except json.JSONDecodeError:
        return result.stdout


def get_tenancy():
    """Get tenancy OCID from config file."""
    import configparser

    cp = configparser.ConfigParser()
    cp.read(CONFIG_FILE)
    return cp.get("DEFAULT", "tenancy")


def get_compartment(tenancy_id):
    """Get the root compartment (same as tenancy for free tier)."""
    return tenancy_id


def get_availability_domains(compartment_id):
    """List all availability domains in the region."""
    print("Fetching availability domains...")
    result = run_oci([
        "iam", "availability-domain", "list",
        "--compartment-id", compartment_id,
    ])
    if not result or "data" not in result:
        print("ERROR: Could not fetch availability domains")
        sys.exit(1)

    ads = [ad["name"] for ad in result["data"]]
    print(f"  Found {len(ads)} ADs: {', '.join(ads)}")
    return ads


def get_ubuntu_image(compartment_id):
    """Find the latest Ubuntu 22.04 ARM64 image."""
    print("Searching for Ubuntu 22.04 ARM64 image...")
    result = run_oci([
        "compute", "image", "list",
        "--compartment-id", compartment_id,
        "--operating-system", "Canonical Ubuntu",
        "--operating-system-version", "22.04",
        "--shape", SHAPE,
        "--sort-by", "TIMECREATED",
        "--sort-order", "DESC",
    ])
    if not result or "data" not in result or not result["data"]:
        # Fallback: try without shape filter
        result = run_oci([
            "compute", "image", "list",
            "--compartment-id", compartment_id,
            "--operating-system", "Canonical Ubuntu",
            "--operating-system-version", "22.04",
            "--sort-by", "TIMECREATED",
            "--sort-order", "DESC",
        ])

    if not result or "data" not in result or not result["data"]:
        print("ERROR: Could not find Ubuntu 22.04 image")
        sys.exit(1)

    # All images returned with shape filter are ARM64 already, just pick the newest
    images = result["data"]
    image_id = images[0]["id"]
    print(f"  Using image: {images[0]['display-name']}")
    return image_id


def create_vcn(compartment_id):
    """Create a VCN with internet gateway and public subnet."""
    print("Creating VCN...")

    vcn_cidr = "10.0.0.0/16"

    # Create VCN
    result = run_oci([
        "network", "vcn", "create",
        "--compartment-id", compartment_id,
        "--display-name", "pms-vcn",
        "--cidr-block", vcn_cidr,
        "--dns-label", "pmsvcn",
    ])
    if not result or "data" not in result:
        print("ERROR: Failed to create VCN")
        sys.exit(1)

    vcn_id = result["data"]["id"]
    print(f"  VCN created: {vcn_id}")

    # Wait for VCN to be available
    print("  Waiting for VCN to become available...", end="", flush=True)
    for _ in range(30):
        vcn = run_oci(["network", "vcn", "get", "--vcn-id", vcn_id])
        if vcn and "data" in vcn and vcn["data"].get("lifecycle-state") == "AVAILABLE":
            print(" AVAILABLE")
            break
        print(".", end="", flush=True)
        time.sleep(2)
    else:
        print(" TIMEOUT")

    # Create Internet Gateway
    print("  Creating Internet Gateway...")
    igw = run_oci([
        "network", "internet-gateway", "create",
        "--compartment-id", compartment_id,
        "--vcn-id", vcn_id,
        "--display-name", "pms-igw",
        "--is-enabled", "true",
    ])
    if igw and "data" in igw:
        igw_id = igw["data"]["id"]
        print(f"  Internet Gateway created: {igw_id}")
    else:
        print("  WARNING: Could not create Internet Gateway")

    # Create route table (or update default)
    print("  Setting up route table...")
    rts = run_oci(["network", "route-table", "list", "--compartment-id", compartment_id, "--vcn-id", vcn_id])
    if rts and "data" in rts and rts["data"]:
        rt_id = rts["data"][0]["id"]
        route_rules = [{
            "cidrBlock": "0.0.0.0/0",
            "networkEntityId": igw["data"]["id"] if igw and "data" in igw else "",
        }]
        run_oci([
            "network", "route-table", "update",
            "--rt-id", rt_id,
            "--route-rules", json.dumps(route_rules),
            "--force",
        ])
        print("  Route table updated with internet gateway")

    # Create public subnet
    print("  Creating public subnet...")
    subnet = run_oci([
        "network", "subnet", "create",
        "--compartment-id", compartment_id,
        "--vcn-id", vcn_id,
        "--display-name", "pms-public-subnet",
        "--cidr-block", "10.0.0.0/24",
        "--dns-label", "pmssubnet",
        "--prohibit-public-ip-on-vnic", "false",
    ])
    if not subnet or "data" not in subnet:
        print("ERROR: Failed to create subnet")
        sys.exit(1)

    subnet_id = subnet["data"]["id"]
    print(f"  Subnet created: {subnet_id}")

    # Wait for subnet to be available
    print("  Waiting for subnet to become available...", end="", flush=True)
    for _ in range(30):
        sn = run_oci(["network", "subnet", "get", "--subnet-id", subnet_id])
        if sn and "data" in sn and sn["data"].get("lifecycle-state") == "AVAILABLE":
            print(" AVAILABLE")
            break
        print(".", end="", flush=True)
        time.sleep(2)
    else:
        print(" TIMEOUT")

    return subnet_id


def get_subnet(compartment_id):
    """Find or create a public subnet in the VCN."""
    print("Searching for public subnet...")

    # List VCNs
    vcns = run_oci(["network", "vcn", "list", "--compartment-id", compartment_id])
    if not vcns or "data" not in vcns or not vcns["data"]:
        print("  No VCNs found, creating one...")
        return create_vcn(compartment_id)

    vcn_id = vcns["data"][0]["id"]
    print(f"  Found VCN: {vcns['data'][0]['display-name']}")

    # List subnets
    subnets = run_oci(["network", "subnet", "list", "--compartment-id", compartment_id, "--vcn-id", vcn_id])
    if not subnets or "data" not in subnets or not subnets["data"]:
        print("  No subnets found in VCN, creating one...")
        return create_vcn(compartment_id)

    # Find a public subnet
    for subnet in subnets["data"]:
        if not subnet.get("prohibit-public-ip-on-vnic", True):
            subnet_id = subnet["id"]
            print(f"  Using public subnet: {subnet['display-name']}")
            return subnet_id

    # Fallback to first subnet
    subnet_id = subnets["data"][0]["id"]
    print(f"  Using subnet: {subnets['data'][0]['display-name']}")
    return subnet_id


def ensure_security_rules(compartment_id):
    """Ensure security list has ports 80, 443, 8000 open."""
    print("Checking security list rules...")

    # Get VCN
    vcns = run_oci(["network", "vcn", "list", "--compartment-id", compartment_id])
    if not vcns or not vcns["data"]:
        print("  WARNING: No VCNs found, skipping security rules")
        return

    vcn_id = vcns["data"][0]["id"]

    # Get security lists
    sls = run_oci(["network", "security-list", "list", "--compartment-id", compartment_id, "--vcn-id", vcn_id])
    if not sls or not sls["data"]:
        print("  WARNING: No security lists found")
        return

    sl = sls["data"][0]
    sl_id = sl["id"]
    existing_rules = sl.get("ingress-security-rules", [])

    # Check which ports are already open
    open_ports = set()
    for rule in existing_rules:
        tcp_opts = rule.get("tcp-options") or {}
        ports = tcp_opts.get("destination-port-range") or {}
        if ports:
            open_ports.add(int(ports.get("min", 0)))

    needed_ports = [80, 443, 8000]
    missing = [p for p in needed_ports if p not in open_ports]

    if not missing:
        print("  All required ports already open")
        return

    print(f"  Adding ingress rules for ports: {missing}")

    # Build new ingress rules (append to existing)
    new_ingress = list(existing_rules)
    for port in missing:
        new_ingress.append({
            "source": "0.0.0.0/0",
            "protocol": "6",
            "tcpOptions": {
                "destinationPortRange": {
                    "min": port,
                    "max": port,
                }
            },
            "description": f"PMS port {port}",
        })

    run_oci([
        "network", "security-list", "update",
        "--security-list-id", sl_id,
        "--ingress-security-rules", json.dumps(new_ingress),
        "--force",
    ])
    print(f"  Security list updated with ports: {missing}")


def create_instance(ad, compartment_id, image_id, subnet_id, ssh_pub_key):
    """Attempt to create a VM instance in the given AD."""
    shape_config = json.dumps({"ocpus": OCPUS, "memoryInGBs": MEMORY_GB})
    source_details = json.dumps({
        "sourceType": "image",
        "imageId": image_id,
        "bootVolumeSizeInGBs": BOOT_VOLUME_GB,
    })

    with open(ssh_pub_key, "r") as f:
        ssh_key_content = f.read().strip()

    result = run_oci([
        "compute", "instance", "launch",
        "--availability-domain", ad,
        "--compartment-id", compartment_id,
        "--display-name", VM_NAME,
        "--shape", SHAPE,
        "--shape-config", shape_config,
        "--source-details", source_details,
        "--subnet-id", subnet_id,
        "--assign-public-ip", "true",
        "--ssh-authorized-keys", ssh_key_content,
        "--metadata", json.dumps({"ssh_authorized_keys": ssh_key_content}),
    ], check=False)

    return result


def get_instance_public_ip(instance_id):
    """Get the public IP of a running instance."""
    # Wait for instance to be running
    print("Waiting for instance to provision...", end="", flush=True)
    for _ in range(60):
        result = run_oci(["compute", "instance", "get", "--instance-id", instance_id])
        if result and "data" in result:
            state = result["data"]["lifecycle-state"]
            if state == "RUNNING":
                print(" RUNNING")
                break
        print(".", end="", flush=True)
        time.sleep(5)
    else:
        print(" TIMEOUT")
        return None

    # Get VNIC attachments
    vnics = run_oci([
        "compute", "instance", "list-vnic-attachments",
        "--instance-id", instance_id,
    ])

    if vnics and "data" in vnics and vnics["data"]:
        vnic_id = vnics["data"][0].get("vnic-id")
        if vnic_id:
            vnic = run_oci(["network", "vnic", "get", "--vnic-id", vnic_id])
            if vnic and "data" in vnic:
                ip = vnic["data"].get("public-ip")
                if ip:
                    return ip

    return None


def main():
    print("=" * 60)
    print("  PMS Oracle Cloud VM Creation Script")
    print("=" * 60)

    # Check SSH key
    if not os.path.exists(SSH_PUB_KEY):
        print(f"\nERROR: SSH public key not found at {SSH_PUB_KEY}")
        print("Generate it with: ssh-keygen -t ed25519 -f ~/.ssh/pms-vm-key -N ''")
        sys.exit(1)

    # Get tenancy and compartment
    tenancy_id = get_tenancy()
    compartment_id = get_compartment(tenancy_id)
    print(f"\nTenancy: {tenancy_id}")
    print(f"Compartment: {compartment_id}")

    # Get availability domains
    ads = get_availability_domains(compartment_id)

    # Get Ubuntu image
    image_id = get_ubuntu_image(compartment_id)

    # Get subnet
    subnet_id = get_subnet(compartment_id)

    # Ensure security rules
    ensure_security_rules(compartment_id)

    # Try creating instance across ADs with retry
    print(f"\n{'=' * 60}")
    print(f"  Attempting VM creation (retry every {RETRY_INTERVAL_SEC}s)")
    print(f"  Shape: {SHAPE} ({OCPUS} OCPU, {MEMORY_GB} GB RAM)")
    print(f"  Boot volume: {BOOT_VOLUME_GB} GB")
    print(f"  Max retries: {MAX_RETRIES} ({MAX_RETRIES * RETRY_INTERVAL_SEC // 60} min)")
    print(f"{'=' * 60}\n")

    attempt = 0
    while attempt < MAX_RETRIES:
        for ad in ads:
            attempt += 1
            print(f"[Attempt {attempt}/{MAX_RETRIES}] Trying {ad}...")

            result = create_instance(ad, compartment_id, image_id, subnet_id, SSH_PUB_KEY)

            if result and "data" in result:
                instance_id = result["data"]["id"]
                print(f"\n✅ Instance created successfully!")
                print(f"   Instance ID: {instance_id}")
                print(f"   AD: {ad}")

                # Get public IP
                public_ip = get_instance_public_ip(instance_id)
                if public_ip:
                    print(f"\n   Public IP: {public_ip}")
                    print(f"\n   SSH: ssh -i ~/.ssh/pms-vm-key ubuntu@{public_ip}")
                    print(f"   URL: http://{public_ip}")
                else:
                    print("\n   Could not retrieve public IP automatically.")
                    print("   Check OCI Console for the instance's public IP.")

                print(f"\n{'=' * 60}")
                print("  VM Created! Next steps:")
                print(f"{'=' * 60}")
                print(f"  1. SSH:  ssh -i ~/.ssh/pms-vm-key ubuntu@{public_ip or 'VM_IP'}")
                print(f"  2. Open iptables ports (see deployment guide)")
                print(f"  3. Clone repo, set up backend + frontend")
                print(f"  4. Configure Nginx + systemd")
                print()

                return

            # Check if it's a capacity error
            print(f"  ❌ Failed (likely out of capacity)")

        if attempt < MAX_RETRIES:
            print(f"\n  Retrying in {RETRY_INTERVAL_SEC} seconds...\n")
            time.sleep(RETRY_INTERVAL_SEC)

    print(f"\n❌ Failed after {MAX_RETRIES} attempts. Try again later or use AMD shape.")


if __name__ == "__main__":
    main()
