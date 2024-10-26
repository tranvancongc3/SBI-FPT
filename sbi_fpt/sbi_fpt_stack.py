from aws_cdk import (
    aws_ec2 as ec2,
    aws_ssm as ssm,
    Stack,
    Tags
)

import aws_cdk as cdk

from constructs import Construct

class SbiFptStack(Stack):

    def __init__(self, scope: Construct, construct_id: str,context: dict, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.context_global = context["env"]
        vpc_config = context['vpc']

        # Create VPC
        vpc = ec2.Vpc(self, "Vpc",
            vpc_name=f"{self.context_global['prefix']}-{self.context_global['environment']}-vpc",
            ip_addresses=ec2.IpAddresses.cidr(vpc_config['cidr']),
            max_azs=vpc_config['maxAZs'],
            subnet_configuration=[]
        )

        # Output to store VPC and subnet information
        output = {
            'vpc': vpc,
            'publicSubnets': [],
            'privateSubnets': []
        }
        
        
        # Create Key Pair
        # key_pair = ec2.CfnKeyPair(self, "BastionKeyPair",
        #     key_name="sbi-fpt-key-name",
        #     key_type="rsa"
        # )
        
        # Generate subnets
        self.gen_subnet(vpc_config['subnets'], vpc, context, output)

        # Create sg
        ec2_sg = ec2.SecurityGroup(self, "Ec2SecurityGroup", vpc=vpc)
        
        # Define CfnOutput for VPC
        cdk.CfnOutput(self, "VpcId",
            value=vpc.vpc_id,
            description="The id of the VPC",
            export_name=f"{self.context_global['prefix']}-{self.context_global['environment']}-vpcId"
        )

    def gen_subnet(self, subnet_props, vpc, context, output):
        # Create Internet Gateway
        cfn_internet_gateway = ec2.CfnInternetGateway(self, "InternetGateway")
        cfn_gateway_attach = ec2.CfnVPCGatewayAttachment(self, "VPCGatewayAttachment",
            vpc_id=vpc.vpc_id,
            internet_gateway_id=cfn_internet_gateway.attr_internet_gateway_id
        )

        nat = None
        public_subnet_count = 1
        private_subnet_count = 1

        for net in subnet_props:
            if net["type"] == "public":
                print(f"Create public subnet with cidr: {net['cidr']}")
                public_subnet = ec2.PublicSubnet(self, f"{self.context_global['prefix']}-{self.context_global['environment']}-PublicSubnet{public_subnet_count}",
                    availability_zone=net["availabilityZone"],
                    cidr_block=net["cidr"],
                    vpc_id=vpc.vpc_id
                )

                # Add Internet Gateway to public subnet
                public_subnet.add_default_internet_route(
                    cfn_internet_gateway.attr_internet_gateway_id,
                    gateway_attachment=cfn_gateway_attach)

                if public_subnet_count == 1:
                    # Create NAT Gateway
                    nat = public_subnet.add_nat_gateway()

                    # Create Bastion Security Group
                    bastion_sg = ec2.SecurityGroup(self, "BastionSG", vpc=vpc)
                    bastion_sg.add_ingress_rule(ec2.Peer.ipv4("0.0.0.0/0"), ec2.Port.tcp(22))

                    # Bastion Instance
                    bastion_instance = ec2.Instance(self, "Bastion",
                        vpc=vpc,
                        vpc_subnets=ec2.SubnetSelection(subnets=[public_subnet]),
                        security_group=bastion_sg,
                        instance_type=ec2.InstanceType.of(
                            ec2.InstanceClass.BURSTABLE2,
                            ec2.InstanceSize.MICRO
                        ),
                        machine_image=ec2.AmazonLinuxImage(
                            generation=ec2.AmazonLinuxGeneration.AMAZON_LINUX_2
                        ),
                        key_name="sbi-fpt-key-name"
                    )

                    # Allocate EIP for the Bastion Host
                    ec2.CfnEIP(self, "BastionEip", instance_id=bastion_instance.instance_id)

                public_subnet_count += 1
                output['publicSubnets'].append(public_subnet)

            if net["type"] == "private":
                print(f"Create private subnet with cidr: {net['cidr']}")
                private_subnet = ec2.PrivateSubnet(self, f"{self.context_global['prefix']}-{self.context_global['environment']}-PrivateSubnet{private_subnet_count}",
                    availability_zone=net["availabilityZone"],
                    cidr_block=net["cidr"],
                    vpc_id=vpc.vpc_id
                )

                # Add NAT Gateway route to private subnet
                private_subnet.add_default_nat_route(nat.attr_nat_gateway_id)

                private_subnet_count += 1
                output['privateSubnets'].append(private_subnet)

        # Add tags to the subnets
        for subnet in output['publicSubnets'] + output['privateSubnets']:
            cdk.Tags.of(subnet).add(
                "Name",
                f"{vpc.node.id}-{subnet.node.id.replace('Subnet', '')}-{subnet.availability_zone}"
            )
