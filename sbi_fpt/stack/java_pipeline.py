from aws_cdk import (
    Stack,
    CfnOutput,
    RemovalPolicy,
    aws_codepipeline as codepipeline,
    aws_codepipeline_actions as actions,
    aws_codebuild as codebuild,
    aws_iam as iam,
    aws_s3 as s3,
    aws_ec2 as ec2,
    aws_autoscaling as autoscaling,
    aws_elasticloadbalancingv2 as elbv2,
    aws_codedeploy as codedeploy,
    Fn
)
import aws_cdk as cdk
from constructs import Construct


class PipelineJavaStack(Stack):
    
    def __init__(self, scope: Construct, construct_id: str,context: dict, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        
        
        # ########## Global context ##################
        global_context = context["env"]
        trigger_on_push = global_context["environment"] != "prod"

        # ########## Codepipeline context ##################
        codepipeline_context = context["java"]

        print(f"Global context: {global_context}")
        print(f"CodePipeline context: {codepipeline_context}")

        
        # ########### Create IAM Role for CodePipeline ################
        pipeline_role = iam.Role(self, "PipelineRole",
            assumed_by=iam.ServicePrincipal("codepipeline.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AWSCodePipeline_FullAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AutoScalingFullAccess"),
            ]
        )
        
        pipeline_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "codedeploy:CreateDeployment",
                "codedeploy:RegisterApplicationRevision",
                "codedeploy:GetDeployment",
                "codedeploy:GetApplication",
                "codedeploy:GetDeploymentGroup",
                "autoscaling:DescribeAutoScalingGroups",
                "autoscaling:DescribeAutoScalingInstances",
                "autoscaling:UpdateAutoScalingGroup",
                "autoscaling:CreateAutoScalingGroup",
                "autoscaling:DeleteAutoScalingGroup"
            ],
            resources=["arn:aws:codedeploy:ap-southeast-1:339712933936:deploymentgroup:sbi-fpt-dev-code-deploy-app/sbi-fpt-dev-deployment-group"]
        ))

        # ########### Create IAM Role for CodeBuild ################
        build_role = iam.Role(self, "CodeBuildRole",
            assumed_by=iam.ServicePrincipal("codebuild.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AWSCodeBuildAdminAccess")
            ]
        )
        
        # # ########### Create IAM Role for CodeDeploy ################
        codedeploy_role = iam.Role(self, "CodeDeployRole",
            assumed_by=iam.ServicePrincipal("codedeploy.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AWSCodeDeployFullAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AutoScalingFullAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AWSCodePipeline_FullAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AmazonEC2RoleforSSM")
            ]
        )
        
        codedeploy_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "codedeploy:GetDeploymentConfig",
                "codedeploy:GetApplicationRevision",
                "codedeploy:CreateDeployment",
                "codedeploy:RegisterApplicationRevision",
                "codedeploy:GetDeployment",
                "codedeploy:GetApplication",
                "codedeploy:GetDeploymentGroup",
                "codedeploy:UpdateDeploymentGroup",
                "codedeploy:ListDeploymentConfigs",
                "codedeploy:ListDeployments",
                "autoscaling:DescribeAutoScalingGroups",
                "autoscaling:DescribeAutoScalingInstances",
                "autoscaling:UpdateAutoScalingGroup",
                "autoscaling:CreateAutoScalingGroup",
                "autoscaling:DeleteAutoScalingGroup"
            ],
            # resources=["arn:aws:codedeploy:ap-southeast-1:339712933936:deploymentgroup:sbi-fpt-dev-code-deploy-app/sbi-fpt-dev-deployment-group"]
            resources=["*"]
        ))
        
        pipeline_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "codedeploy:GetDeploymentConfig",
                "codedeploy:GetApplicationRevision",
                "codedeploy:CreateDeployment",
                "codedeploy:RegisterApplicationRevision",
                "codedeploy:GetDeployment",
                "codedeploy:GetApplication",
                "codedeploy:GetDeploymentGroup",
                "codedeploy:UpdateDeploymentGroup",
                "codedeploy:ListDeploymentConfigs",
                "codedeploy:ListDeployments"
            ],
            # resources=["arn:aws:codedeploy:ap-southeast-1:339712933936:deploymentgroup:sbi-fpt-dev-code-deploy-app/sbi-fpt-dev-deployment-group"]
            resources=["*"]
        ))

        # ########## S3 Bucket for Artifacts ##################
        artifact_admin_bucket = s3.Bucket(self, "ArtifactBucket",
            bucket_name=f"{global_context['prefix']}-{global_context['environment']}-backend-codepipeline",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True
        )

        # ########### CodePipeline ################
        pipeline = codepipeline.Pipeline(self, "Pipeline",
            pipeline_name=f"{global_context['prefix']}-{global_context['environment']}-{codepipeline_context['name']}-pipeline",
            artifact_bucket=artifact_admin_bucket,
            role=pipeline_role
        )

        # Source backend
        source = codepipeline.Artifact("SourceArtifact_backend")

        source_backend = actions.CodeStarConnectionsSourceAction(
            action_name="Github_Source",
            owner=codepipeline_context["owner"],
            repo=codepipeline_context["repo"],
            branch=codepipeline_context["branch"],
            connection_arn=codepipeline_context["connectionArn"],
            trigger_on_push=trigger_on_push,
            output=source,
        )

        pipeline.add_stage(
            stage_name="Source",
            actions=[source_backend],
        )

        # ############### CodeBuild ###############
        build_project = codebuild.PipelineProject(self, "BuildProject",
            project_name=f"translate-gpt-backend-{global_context['environment']}",
            build_spec=codebuild.BuildSpec.from_source_filename("buildspec.yaml"),
            environment={
                "build_image": codebuild.LinuxBuildImage.from_code_build_image_id("aws/codebuild/standard:7.0"),
                "environment_variables": {
                    "ENV_FILE": {
                        "type": codebuild.BuildEnvironmentVariableType.PARAMETER_STORE,
                        "value": codepipeline_context["paramaterStoreEnv"]
                    },
                },
                "privileged": True,
            },
            role=build_role
        )

        build_artifact = codepipeline.Artifact("BuildArtifact")

        build_action = actions.CodeBuildAction(
            action_name="Build",
            project=build_project,
            input=source,
            outputs=[build_artifact]
        )

        # ########## Build stage ############
        pipeline.add_stage(
            stage_name="Build",
            actions=[build_action]
        )
        
        
        
        
        
        

        # ########## Deployment Stage - Blue-Green Deployment with WAR file copy ##########
        # Existing Auto Scaling Group and Load Balancer
        load_balancer_arn = Fn.import_value("loadbalancerarn")
        asg_name = Fn.import_value("asgname")
        target_group_arn = Fn.import_value("targetgrouparn")
        print(target_group_arn)
        target_group = elbv2.ApplicationTargetGroup.from_target_group_attributes(self, "ImportedTargetGroup",
            target_group_arn="arn:aws:elasticloadbalancing:ap-southeast-1:339712933936:targetgroup/sbi-fp-myALB-PIPXCZCL8XG8/be05707c4c6c0d84",
            load_balancer_arns="arn:aws:elasticloadbalancing:ap-southeast-1:339712933936:loadbalancer/app/sbi-fpt-dev-alb/a109af08a83a01ca",
        )
        
        autoscaling_group = autoscaling.AutoScalingGroup.from_auto_scaling_group_name(self, "asggroup",
            auto_scaling_group_name="sbi-fpt-dev-asg-blue")
        
        # Create CodeDeploy application
        application = codedeploy.ServerApplication(self, "CodeDeployApplication",
            application_name=f"{global_context['prefix']}-{global_context['environment']}-code-deploy-app"
        )
        
        # blue_green_config = codedeploy.CfnDeploymentGroup.BlueGreenDeploymentConfigurationProperty(
        #     deployment_ready_option=codedeploy.CfnDeploymentGroup.DeploymentReadyOptionProperty(
        #         action_on_timeout="STOP_DEPLOYMENT",
        #         wait_time_in_minutes=5
        #     ),
        #     green_fleet_provisioning_option=codedeploy.CfnDeploymentGroup.GreenFleetProvisioningOptionProperty(
        #         action="DISCOVER_EXISTING"
        #         # action="COPY_AUTO_SCALING_GROUP"
        #     ),
        #     terminate_blue_instances_on_deployment_success=codedeploy.CfnDeploymentGroup.BlueInstanceTerminationOptionProperty(
        #         action="TERMINATE",
        #         termination_wait_time_in_minutes=5
        #     )
        # )
        
        load_balancer_info = codedeploy.CfnDeploymentGroup.LoadBalancerInfoProperty(
            elb_info_list=[codedeploy.CfnDeploymentGroup.ELBInfoProperty(
                name="sbi-fpt-dev-alb"
            )],
            target_group_info_list=[codedeploy.CfnDeploymentGroup.TargetGroupInfoProperty(
                name="sbi-fp-myALB-PIPXCZCL8XG8"
            )],
            target_group_pair_info_list=[codedeploy.CfnDeploymentGroup.TargetGroupPairInfoProperty(
                prod_traffic_route=codedeploy.CfnDeploymentGroup.TrafficRouteProperty(
                    listener_arns=["arn:aws:elasticloadbalancing:ap-southeast-1:339712933936:listener/app/sbi-fpt-dev-alb/a109af08a83a01ca/eaab145e9d1173d8"]
                ),
                target_groups=[codedeploy.CfnDeploymentGroup.TargetGroupInfoProperty(
                    name="sbi-fp-myALB-CTUD8LZ7YAYZ"
                )],
                test_traffic_route=codedeploy.CfnDeploymentGroup.TrafficRouteProperty(
                    listener_arns=["arn:aws:elasticloadbalancing:ap-southeast-1:339712933936:listener/app/sbi-fpt-dev-alb/a109af08a83a01ca/eaab145e9d1173d8"]
                )
            )]
        )
        
        
        
        deployment_group = codedeploy.CfnDeploymentGroup(self, "aa",
            application_name=application.application_name,
            service_role_arn=codedeploy_role.role_arn,
            deployment_group_name=f"{global_context['prefix']}-{global_context['environment']}-deployment-group",
            deployment_config_name="CodeDeployDefault.OneAtATime",
            auto_scaling_groups=["sbi-fpt-dev-asg-blue"],
            # deployment_style=codedeploy.CfnDeploymentGroup.DeploymentStyleProperty(
            #     deployment_option="WITHOUT_TRAFFIC_CONTROL",
            #     deployment_type="BLUE_GREEN"
            # ),
            load_balancer_info=load_balancer_info,
            blue_green_deployment_configuration=codedeploy.CfnDeploymentGroup.BlueGreenDeploymentConfigurationProperty(
                deployment_ready_option=codedeploy.CfnDeploymentGroup.DeploymentReadyOptionProperty(
                    action_on_timeout="STOP_DEPLOYMENT",
                    wait_time_in_minutes=1
                ),
                green_fleet_provisioning_option=codedeploy.CfnDeploymentGroup.GreenFleetProvisioningOptionProperty(
                    # action="DISCOVER_EXISTING"
                    action="COPY_AUTO_SCALING_GROUP"
                ),
                terminate_blue_instances_on_deployment_success=codedeploy.CfnDeploymentGroup.BlueInstanceTerminationOptionProperty(
                    action="TERMINATE",
                    termination_wait_time_in_minutes=0
                )
            ),
            termination_hook_enabled=True
        )
        
        
        # deployment_group.add_property_override(
        #     "deployment_option",
        #     ["WITHOUT_TRAFFIC_CONTROL"]  # Reference the ASG name
        # )
        # deployment_style=codedeploy.CfnDeploymentGroup.DeploymentStyleProperty(
        #         deployment_option="WITHOUT_TRAFFIC_CONTROL",
        #         deployment_type="BLUE_GREEN"
        #     ),
        
        
        # deployment_group.add_property_override
        
        # deployment_group.DeploymentStyleProperty(
        #     deployment_option="WITH_TRAFFIC_CONTROL",
        #     deployment_type="BLUE_GREEN"
        # )
        
        # deployment_style=codedeploy.CfnDeploymentGroup.DeploymentStyleProperty(
        #         deployment_option="WITHOUT_TRAFFIC_CONTROL",
        #         deployment_type="BLUE_GREEN"
        #     ),
        
        
        
        # deployment_config = codedeploy.ServerDeploymentConfig(self, "DeploymentConfiguration",
        #     deployment_config_name="MyDeploymentConfiguration",  # optional property
        #     # one of these is required, but both cannot be specified at the same time
        #     minimum_healthy_hosts=codedeploy.MinimumHealthyHosts.count(1),
        #     zonal_config=codedeploy.ZonalConfig(
        #         monitor_duration=cdk.Duration.minutes(30),
        #         first_zone_monitor_duration=cdk.Duration.minutes(60),
        #         minimum_healthy_hosts_per_zone=codedeploy.MinimumHealthyHostsPerZone.count(1)
        #     )
        # )
        
        
        # # # Deployment action in CodePipeline
        # deploy_action = actions.CodeDeployServerDeployAction(
        #     action_name="BlueGreenDeploy",
        #     deployment_group=deployment_group,
        #     input=build_artifact,
        # )

        # # Add Deploy stage
        # pipeline.add_stage(
        #     stage_name="Deploy",
        #     actions=[
        #              actions.CodeDeployServerDeployAction(
        #                 action_name="BlueGreenDeploy",
        #                 deployment_group=deployment_group,
        #                 input=build_artifact,
        #             )]
        # )
        
        # codepipeline.StageProps(
        #     stage_name="Deploy",
        #     actions=[
        #         pipeline.CodeDeployServerDeployAction(
        #             action_name="Deploy",
        #             input=build_artifact,
        #             deployment_group=deployment_group
        #         )
        #     ]
        # )
