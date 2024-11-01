from aws_cdk import (
    aws_ec2 as ec2,
    aws_elasticloadbalancingv2 as elbv2,
    aws_autoscaling as autoscaling,
    aws_iam as iam,
    aws_s3 as s3,
    aws_cloudwatch as cloudwatch,
    aws_sns as sns,
    Stack,
    RemovalPolicy,
    CfnOutput,
)
import aws_cdk as cdk
from cdk_nag import NagSuppressions
from constructs import Construct


class JavaStack(Stack):

    def __init__(self, scope: Construct, construct_id: str,context: dict, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        context_global = context["env"]
        vpc_config = context["vpc"]
        vpc = ec2.Vpc.from_lookup(self, "ImportedVpc", vpc_id=vpc_config["vpc_id"])
        backend = context["java"]
        ec2_sg = backend["sg"]
        key_name = backend["key_name"]
        
        
        # Create S3 bucket for ALB access logs
        
        NagSuppressions.add_stack_suppressions(self, [
            {
                'id': 'AwsSolutions-S10',
                'reason': 'The S3 Bucket or bucket policy does not require requests to use SSL',
            },
        ])
        
        log_alb = s3.Bucket(self, "logLoadbalancer",
            bucket_name=f"{context_global['prefix']}-{context_global['environment']}-alb-log",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            versioned=True,
            server_access_logs_prefix="logs",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )
        
        log_alb.add_to_resource_policy(iam.PolicyStatement(
            effect=iam.Effect.DENY,
            actions=["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
            resources=[log_alb.bucket_arn, f"{log_alb.bucket_arn}/*"],
            principals=[iam.ArnPrincipal("*")],
            conditions={
                "Bool": {
                    "aws:SecureTransport": "false"
                }
            }
        ))
        
        # Create Application Load Balancer
        alb = elbv2.ApplicationLoadBalancer(self, "myALB",
            vpc=vpc,
            internet_facing=True,
            load_balancer_name=f"{context_global["prefix"]}-{context_global["environment"]}-alb"
            )
        
        alb.log_access_logs(log_alb)
        alb.connections.allow_from_any_ipv4(ec2.Port.tcp(80), "Internet access ALB 80")
        
        NagSuppressions.add_resource_suppressions(
            alb,
            [
                {
                    'id': 'AwsSolutions-EC23',
                    'reason': 'The ALB is required to provide public access for a web application that needs to be accessed globally.',
                },
            ],
            True
        )
        
        listener = alb.add_listener("mylistener",
            port=80,
            open=True)
        
        # Create Launch Template
        role = iam.Role(self, "roleLaunchTemplate",
            role_name=f"{context_global["prefix"]}-{context_global["environment"]}-launch-template-role",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEC2FullAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AutoScalingFullAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AmazonEC2RoleforAWSCodeDeploy"),
            ]
        )
        
        # Add custom policy to allow KMS decrypt
        role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["kms:Decrypt"],
            resources=["*"]
        ))
        
        NagSuppressions.add_resource_suppressions(
            role,
            [
                {
                    'id': 'AwsSolutions-IAM4',
                    'reason': 'Using wildcard permissions for SSM, needed for operational flexibility.',
                },
            ],
            True
        )
        
        NagSuppressions.add_resource_suppressions(
            role,
            [
                {
                    'id': 'AwsSolutions-IAM5',
                    'reason': 'Skip the soulution',
                },
            ],
            True
        )
        
        
        launch_template = ec2.LaunchTemplate(self, "LaunchTemplate",
            launch_template_name=f"{context_global["prefix"]}-{context_global["environment"]}-launch-template",
            instance_type=ec2.InstanceType(backend["instanceType"]),
            machine_image=ec2.MachineImage.generic_linux({
                f"{self.region}": backend["ami"]
            }),
            security_group=ec2.SecurityGroup.from_security_group_id(self, "SG", ec2_sg),
            role=role,
            key_name=key_name,
        )
        
         # Configure Auto Scaling Notifications
        
        sns_topic = sns.Topic(self, "AutoScalingNotifications")
        
        NagSuppressions.add_resource_suppressions(
            sns_topic,
            [
                {
                    'id': 'AwsSolutions-SNS3',
                    'reason': 'Skip the error sns',
                },
            ],
            True
        )
        
        policy_document = iam.PolicyDocument(
            assign_sids=True,
            statements=[
                iam.PolicyStatement(
                    actions=["sns:Publish"],
                    resources=[sns_topic.topic_arn],
                    effect=iam.Effect.ALLOW,
                    principals=[iam.ArnPrincipal("*")],
                    conditions={
                        "Bool": {
                            "aws:SecureTransport": "true"
                        }
                    }
                )
            ]
        )
        
        topic_policy = sns.TopicPolicy(self, "Policy",
            topics=[sns_topic],
            policy_document=policy_document
        )
        
        # Create Auto Scaling Group
        asg  = autoscaling.AutoScalingGroup(
            self, "blue_asg",
            auto_scaling_group_name=f"{context_global["prefix"]}-{context_global["environment"]}-asg-blue",
            vpc=vpc,
            ssm_session_permissions=True,
            launch_template=launch_template,
            notifications=[autoscaling.NotificationConfiguration(topic=sns_topic)],
            min_capacity=1,
            max_capacity=2,
        )
        
        
        
        
        # Attach ASGs to the Load Balancer Target Groups
        target_group = listener.add_targets("TargetGroup",
            port=8080,
            targets=[asg],
            health_check=elbv2.HealthCheck(
                path="/",
                interval=cdk.Duration.seconds(30),
                timeout=cdk.Duration.seconds(5),
                healthy_threshold_count=2,
                unhealthy_threshold_count=2,
                healthy_http_codes="200"
            )
        )
        
       
        
        
        asg.scale_on_cpu_utilization("CpuScaling",
            target_utilization_percent=70,
            cooldown=cdk.Duration.minutes(5)
        )
        
        
        # asg.add_alarm(sns_topic)
        
        CfnOutput(self, "targetgrouparn",
            value=target_group.target_group_arn,
            export_name= "targetgrouparn",
            description="ARN of the target group",
        )
        
        CfnOutput(self, "loadbalancerarn",
            value=alb.load_balancer_arn,
            export_name= "loadbalancerarn",
            description="ARN of the Application Load Balancer"
        )

        CfnOutput(self, "asgname",
            value=asg.auto_scaling_group_name,
            export_name= "asgname",
            description="Name of the Auto Scaling Group"
        )