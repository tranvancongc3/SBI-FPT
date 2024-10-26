from aws_cdk import (
    aws_ec2 as ec2,
    aws_elasticloadbalancingv2 as elbv2,
    aws_autoscaling as autoscaling,
    aws_iam as iam,
    Stack,
    Environment,
    CfnOutput
)
import aws_cdk as cdk
from constructs import Construct


# with open("./user_data/user_data.sh") as f:
#     user_data = f.read()


class JavaStack(Stack):

    def __init__(self, scope: Construct, construct_id: str,context: dict, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.context_global = context["env"]
        vpc_config = context["vpc"]
        vpc = ec2.Vpc.from_lookup(self, "ImportedVpc", vpc_id=vpc_config["vpc_id"])
        ec2_sg = context["java"]["sg"]
        key_name = context["java"]["key_name"]
        
        
        # Create Application Load Balancer
        alb = elbv2.ApplicationLoadBalancer(self, "myALB",
            vpc=vpc,
            internet_facing=True,
            load_balancer_name=f"{self.context_global["prefix"]}-{self.context_global["environment"]}-alb"
            )
        
        alb.connections.allow_from_any_ipv4(ec2.Port.tcp(80), "Internet access ALB 80")
        
        listener = alb.add_listener("mylistener",
            port=80,
            open=True)
        
        # Create Launch Template
        role = iam.Role(self, "EC2SSMRole",
            role_name=f"{self.context_global["prefix"]}-{self.context_global["environment"]}-ec2-ssm-role",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEC2FullAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AutoScalingFullAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AmazonEC2RoleforAWSCodeDeploy")
            ]
        )
        
        launch_template = ec2.LaunchTemplate(self, "LaunchTemplate",
            launch_template_name=f"{self.context_global["prefix"]}-{self.context_global["environment"]}-launch-template",
            instance_type=ec2.InstanceType("t2.micro"),
            machine_image=ec2.MachineImage.generic_linux({
                "ap-southeast-1": context["java"]["ami"]
            }),
            security_group=ec2.SecurityGroup.from_security_group_id(self, "SG", ec2_sg),
            role=role,
            key_name=key_name,
        )
        
        # Create Auto Scaling Group
        blue_asg  = autoscaling.AutoScalingGroup(
            self, "blue_asg",
            auto_scaling_group_name=f"{self.context_global["prefix"]}-{self.context_global["environment"]}-asg-blue",
            vpc=vpc,
            ssm_session_permissions=True,
            launch_template=launch_template,
            min_capacity=1,
            max_capacity=2,
        )
        
        green_asg  = autoscaling.AutoScalingGroup(
            self, "green_asg",
            auto_scaling_group_name=f"{self.context_global["prefix"]}-{self.context_global["environment"]}-asg-green",
            vpc=vpc,
            ssm_session_permissions=True,
            launch_template=launch_template,
            min_capacity=0,
            max_capacity=2,
        )
        
        
        # Attach ASGs to the Load Balancer Target Groups
        target_group = listener.add_targets("TargetGroup",
            port=8080,
            targets=[blue_asg,green_asg],
            health_check=elbv2.HealthCheck(
                path="/",
                interval=cdk.Duration.seconds(30),
                timeout=cdk.Duration.seconds(5),
                healthy_threshold_count=2,
                unhealthy_threshold_count=2,
                healthy_http_codes="200"
            )
        )
        
        blue_asg.scale_on_cpu_utilization("CpuScaling",
            target_utilization_percent=70,
            cooldown=cdk.Duration.minutes(5)
        )
        
        CfnOutput(self, "targetgrouparn",
            value=target_group.target_group_arn,
            description="ARN of the target group"
        )
        
        CfnOutput(self, "loadbalancerarn",
            value=alb.load_balancer_arn,
            description="DNS name of the Application Load Balancer"
        )

        CfnOutput(self, "asgname",
            value=blue_asg.auto_scaling_group_name,
            description="Name of the Auto Scaling Group"
        )