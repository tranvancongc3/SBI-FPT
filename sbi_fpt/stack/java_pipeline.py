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
    custom_resources as custom_resources,
    aws_kms as kms,
    Fn
)
import aws_cdk as cdk
from constructs import Construct
from cdk_nag import NagSuppressions


class PipelineJavaStack(Stack):
    
    def __init__(self, scope: Construct, construct_id: str,context: dict, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        ########### Global context ##################
        global_context = context["env"]
        trigger_on_push = global_context["environment"] != "prod"

        ########### Codepipeline context ##################
        codepipeline_context = context["java"]
        
        ########### S3 Bucket for Artifacts ##################
        
        NagSuppressions.add_stack_suppressions(self, [
            {
                'id': 'AwsSolutions-S10',
                'reason': 'The S3 Bucket or bucket policy does not require requests to use SSL',
            },
        ])
        
        
        artifact_java_bucket = s3.Bucket(self, "ArtifactBucket",
            bucket_name=f"{global_context['prefix']}-{global_context['environment']}-backend-codepipeline",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            server_access_logs_prefix="logs",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True
        )
        
        ############ Create IAM Role for CodePipeline ################
        
        
        pipeline_role = iam.Role(self, "PipelineRole",
            role_name= f"{global_context['prefix']}-{global_context['environment']}-{codepipeline_context['name']}-pipeline-role",
            assumed_by=iam.ServicePrincipal("codepipeline.amazonaws.com"),
        )
        
        pipeline_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "codedeploy:CreateDeployment",
                "codedeploy:RegisterApplicationRevision",
                "codedeploy:GetDeployment",
                "codedeploy:GetApplication",
                "codedeploy:GetDeploymentGroup",
                "sts:AssumeRole"
            ],
            resources=[
                f"arn:aws:codedeploy:{self.region}:{self.account}:application:{global_context['prefix']}-{global_context['environment']}-code-deploy-app",
                f"arn:aws:codedeploy:{self.region}:{self.account}:deploymentgroup:{global_context['prefix']}-{global_context['environment']}-code-deploy-app/{global_context['prefix']}-{global_context['environment']}-deployment-group"
            ]
        ))
        
        NagSuppressions.add_stack_suppressions(self, [
            {
                'id': 'AwsSolutions-IAM5',
                'reason': 'The S3 Bucket or bucket policy does not require requests to use SSL',
            },
        ])
        ############ Create IAM Role for CodeBuild ################
        build_role = iam.Role(self, "CodeBuildRole",
            role_name= f"{global_context['prefix']}-{global_context['environment']}-{codepipeline_context['name']}-codebuild-role",
            assumed_by=iam.ServicePrincipal("codebuild.amazonaws.com"),
        )

        build_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "s3:GetObject",
                "s3:PutObject",
                "s3:GetBucketLocation",
            ],
            resources=[artifact_java_bucket.bucket_arn, f"{artifact_java_bucket.bucket_arn}/*"]
        ))
        
        ############# Create IAM Role for CodeDeploy ################
        codedeploy_role = iam.Role(self, "CodeDeployRole",
            role_name=f"{global_context['prefix']}-{global_context['environment']}-{codepipeline_context['name']}-codedeploy-role",
            assumed_by=iam.ServicePrincipal("codedeploy.amazonaws.com"),
        )
        
        codedeploy_role.assume_role_policy.add_statements(iam.PolicyStatement(
            actions=["sts:AssumeRole"],
            effect=iam.Effect.ALLOW,
            principals=[iam.ArnPrincipal(pipeline_role.role_arn)]
        ))

        codedeploy_role.add_to_policy(iam.PolicyStatement(
            actions=[
                # Auto Scaling permissions
                "autoscaling:DescribeAutoScalingGroups",
                "autoscaling:UpdateAutoScalingGroup",
                "autoscaling:CreateAutoScalingGroup",
                "autoscaling:DeleteAutoScalingGroup",
                "autoscaling:CreateOrUpdateTags",
                "autoscaling:DeleteTags",
                "autoscaling:PutScalingPolicy",
                "autoscaling:DeleteScalingPolicy",
                "autoscaling:PutLifecycleHook",
                "autoscaling:DeleteLifecycleHook",
                "autoscaling:CompleteLifecycleAction",
                
                # EC2 permissions for Launch Template
                "ec2:RunInstances",
                "ec2:CreateTags",

                # IAM permission to pass roles for EC2 instances
                "iam:PassRole",

                # SNS permissions to publish deployment events
                "sns:Publish",

                # CloudWatch permissions for alarms
                "cloudwatch:DescribeAlarms",
                "cloudwatch:GetMetricStatistics",

                # ELB permissions
                "elasticloadbalancing:DescribeLoadBalancers",
                "elasticloadbalancing:RegisterTargets",
                "elasticloadbalancing:DeregisterTargets",
                "elasticloadbalancing:DescribeTargetGroups",
                "elasticloadbalancing:ModifyTargetGroupAttributes"
            ],
            resources=["*"]
        ))

        codedeploy_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "codedeploy:GetDeploymentConfig",
                "codedeploy:CreateDeployment",
                "codedeploy:GetDeployment",
            ],
            resources=[f"arn:aws:codedeploy:{self.region}:{self.account}:deploymentgroup:{global_context['prefix']}-{global_context['environment']}-code-deploy-app/{global_context['prefix']}-{global_context['environment']}-deployment-group"]
        ))
        
        NagSuppressions.add_stack_suppressions(self, [
            {
                'id': 'AwsSolutions-IAM4',
                'reason': 'The S3 Bucket or bucket policy does not require requests to use SSL',
            },
        ])

        

        ############ CodePipeline ################
        pipeline = codepipeline.Pipeline(self, "Pipeline",
            pipeline_name=f"{global_context['prefix']}-{global_context['environment']}-{codepipeline_context['name']}-pipeline",
            artifact_bucket=artifact_java_bucket,
            role=pipeline_role
        )

        # Source
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

        ################ CodeBuild ###############
        
        kms_key = kms.Key(self, "BuildProjectKey",
                  alias="alias/codebuild/buildprojectkey",
                  enable_key_rotation=True)
        
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
                "privileged": False,
            },
            role=build_role,
            encryption_key=kms_key
        )

        build_artifact = codepipeline.Artifact("BuildArtifact")

        build_action = actions.CodeBuildAction(
            action_name="Build",
            project=build_project,
            input=source,
            outputs=[build_artifact]
        )

        ########### Build stage ############
        pipeline.add_stage(
            stage_name="Build",
            actions=[build_action]
        )

        ########### Deployment Stage - Blue-Green Deployment with WAR file copy ##########
        
        autoscaling_name=Fn.import_value("asgname")
        
        load_balancer_arn=Fn.import_value("loadbalancerarn")
        
        target_group_arn=Fn.import_value("targetgrouparn")
        
        # Create CodeDeploy application
        application = codedeploy.ServerApplication(self, "CodeDeployApplication",
            application_name=f"{global_context['prefix']}-{global_context['environment']}-code-deploy-app"
        )
        
        target_group = elbv2.ApplicationTargetGroup.from_target_group_attributes(
            self, 
            "MyTargetGroup",
            load_balancer_arns=load_balancer_arn,
            target_group_arn=target_group_arn,  
        )
        
        
        deployment_group = codedeploy.ServerDeploymentGroup(self, "deployment",
            application=application,
            role=codedeploy_role,
            deployment_group_name=f"{global_context['prefix']}-{global_context['environment']}-deployment-group",
            deployment_config=codedeploy.ServerDeploymentConfig.ONE_AT_A_TIME,
            load_balancer=codedeploy.LoadBalancer.application(target_group),
            auto_rollback=codedeploy.AutoRollbackConfig(
                failed_deployment=True,
            ),
        )
        
        
        custom_role = iam.Role(
            self, "CustomResourceRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com")
        )
        
        custom_role.add_to_policy(iam.PolicyStatement(
            actions=["codedeploy:UpdateDeploymentGroup"],
            resources=[
                f"arn:aws:codedeploy:{self.region}:{self.account}:application:{global_context['prefix']}-{global_context['environment']}-code-deploy-app",
                f"arn:aws:codedeploy:{self.region}:{self.account}:deploymentgroup:{global_context['prefix']}-{global_context['environment']}-code-deploy-app/{global_context['prefix']}-{global_context['environment']}-deployment-group"
            ]
        ))
        
        update_deployment_style = custom_resources.AwsCustomResource(
            self, "UpdateDeploymentStyle",
            on_create=custom_resources.AwsSdkCall(
                service="CodeDeploy",
                action="updateDeploymentGroup",
                parameters={
                    "applicationName": application.application_name,
                    "currentDeploymentGroupName": deployment_group.deployment_group_name,
                    "deploymentStyle": {
                        "deploymentType": "BLUE_GREEN",
                        "deploymentOption": "WITH_TRAFFIC_CONTROL"
                    },
                    "deploymentConfigName": "CodeDeployDefault.OneAtATime",
                    "autoScalingGroups": [autoscaling_name],
                    "blueGreenDeploymentConfiguration": {
                        "terminateBlueInstancesOnDeploymentSuccess": {
                            "action": "TERMINATE",
                            "terminationWaitTimeInMinutes": 0,
                            },
                        "deploymentReadyOption": {
                            "actionOnTimeout": "CONTINUE_DEPLOYMENT",
                            },
                        "greenFleetProvisioningOption": {
                            "action": "COPY_AUTO_SCALING_GROUP",
                            },
                    },
                },
                physical_resource_id=custom_resources.PhysicalResourceId.of("UpdateDeploymentStyle")
            ),
            policy=custom_resources.AwsCustomResourcePolicy.from_statements([
                iam.PolicyStatement(
                    actions=["codedeploy:UpdateDeploymentGroup"],
                    resources=["*"]
                )
            ]),
            role=custom_role
        )

        deploy_action = actions.CodeDeployServerDeployAction(
            action_name="Deploy",
            input=build_artifact,
            deployment_group=deployment_group,
            role=codedeploy_role
        )
        
        pipeline.add_stage(
            stage_name="deploy",
            actions=[deploy_action]
        )