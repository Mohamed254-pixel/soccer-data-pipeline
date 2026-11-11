"""Render the isolated demo template from reviewed shared infrastructure and timer files."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def render():
    source = json.loads((HERE.parent / "infrastructure.json").read_text())
    names = (
        "Vpc", "InternetGateway", "GatewayAttachment", "ComputeSubnet", "PublicRoutes",
        "InternetRoute", "PublicRouteAssociation", "HostSecurityGroup", "Archive",
        "ArchivePolicy", "RuntimeSecret", "HostRole", "HostProfile", "AirflowHost",
    )
    resources = {name: source["Resources"][name] for name in names}
    resources["Vpc"]["Properties"]["CidrBlock"] = "10.78.0.0/16"
    resources["ComputeSubnet"]["Properties"]["CidrBlock"] = "10.78.0.0/24"
    # Choose from supported Ohio zones when submitting the reviewed parameters.
    resources["ComputeSubnet"]["Properties"]["AvailabilityZone"] = {"Ref": "AvailabilityZone"}
    resources["HostSecurityGroup"]["Properties"]["SecurityGroupEgress"] = [
        {"IpProtocol": "tcp", "FromPort": 443, "ToPort": 443, "CidrIp": "0.0.0.0/0"}
    ]
    archive = resources["Archive"]["Properties"]
    archive["LifecycleConfiguration"]["Rules"].append({
        "Id": "ExpireDemoArchive",
        "Status": "Enabled",
        "Prefix": "raw/",
        "ExpirationInDays": 30,
        "NoncurrentVersionExpiration": {"NoncurrentDays": 7},
    })
    archive["LifecycleConfiguration"]["Rules"].append({
        "Id": "RemoveExpiredDemoMarkers",
        "Status": "Enabled",
        "Prefix": "raw/",
        "ExpiredObjectDeleteMarker": True,
    })
    bucket_policy = resources["ArchivePolicy"]["Properties"]["PolicyDocument"]["Statement"]
    bucket_policy.append({
        "Sid": "RequireConditionalArchivePut",
        "Effect": "Deny",
        "Principal": "*",
        "Action": "s3:PutObject",
        "Resource": {"Fn::Sub": "${Archive.Arn}/raw/*"},
        "Condition": {"StringNotEquals": {"s3:if-none-match": "*"}},
    })
    resources["RuntimeSecret"]["Properties"].update({
        "Name": {"Fn::Sub": "${AWS::StackName}/demo-runtime"},
        "Description": "Demo-only runtime secrets. Populate only after approved setup.",
    })
    role = resources["HostRole"]["Properties"]
    statements = role["Policies"][0]["PolicyDocument"]["Statement"]
    statements.pop()  # This demo uses size-bounded Docker logging and exports evidence over SSM.
    instance = resources["AirflowHost"]["Properties"]
    instance.update({
        "InstanceType": "c7i-flex.large",
        "ImageId": {"Ref": "ReviewedAmi"},
        "InstanceInitiatedShutdownBehavior": "stop",
    })
    instance["MetadataOptions"]["HttpProtocolIpv6"] = "disabled"
    instance["BlockDeviceMappings"][0]["Ebs"].update({"VolumeSize": 20, "DeleteOnTermination": True})

    user_data = [
        "#!/bin/bash\nset -euo pipefail\n"
        "install -d -m 0755 /etc/premier-league-demo\n"
        "now=$(date -u +%s)\nmaximum=$((now + 115140))\napproved=",
        {"Ref": "ApprovedStopEpoch"},
        "\nif (( approved < maximum )); then maximum=$approved; fi\n"
        "printf '%s\\n' \"$maximum\" > /etc/premier-league-demo/deadline\n",
    ]
    files = {
        "shutdown-check.sh": "/usr/local/sbin/premier-league-demo-shutdown",
        "shutdown-check.service": "/etc/systemd/system/premier-league-demo-shutdown.service",
        "shutdown-check.timer": "/etc/systemd/system/premier-league-demo-shutdown.timer",
    }
    for name, destination in files.items():
        user_data.append(f"cat > {destination} <<'DEMO_FILE'\n"
                         + (HERE / name).read_text() + "DEMO_FILE\n")
    user_data.append(
        "chmod 0755 /usr/local/sbin/premier-league-demo-shutdown\n"
        "systemctl daemon-reload\n"
        "systemctl enable --now premier-league-demo-shutdown.timer\n"
    )
    instance["UserData"] = {"Fn::Base64": {"Fn::Join": ["", user_data]}}
    for name in ("AirflowHost", "Vpc", "Archive", "RuntimeSecret"):
        resources[name]["Properties"].setdefault("Tags", []).extend([
            {"Key": "Project", "Value": "premier-league-data-pipeline"},
            {"Key": "Purpose", "Value": "isolated-demo"},
            {"Key": "StopEpochUTC", "Value": {"Ref": "ApprovedStopEpoch"}},
        ])
    return {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": "Isolated 32-hour Premier League demo in Ohio. User data installs only a stop timer.",
        "Parameters": {
            "ReviewedAmi": {"Type": "AWS::EC2::Image::Id", "Description": "Reviewed Ohio x86_64 AL2023 AMI ID"},
            "AvailabilityZone": {"Type": "AWS::EC2::AvailabilityZone::Name",
                                 "AllowedPattern": "us-east-2[a-z]"},
            "ApprovedStopEpoch": {"Type": "String", "AllowedPattern": "[1-9][0-9]{9}",
                                  "Description": "Approved absolute UTC stop deadline as Unix seconds"},
        },
        "Resources": resources,
        "Outputs": {
            "InstanceId": {"Value": {"Ref": "AirflowHost"}},
            "ArchiveBucket": {"Value": {"Ref": "Archive"}},
            "RuntimeSecretArn": {"Value": {"Ref": "RuntimeSecret"}},
        },
    }


if __name__ == "__main__":
    print(json.dumps(render(), indent=2))
