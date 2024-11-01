from aws_cdk import (
    Stack,
    RemovalPolicy,
    aws_codepipeline as codepipeline,
    aws_codepipeline_actions as actions,
    aws_codebuild as codebuild,
    aws_iam as iam,
    aws_s3 as s3,
    aws_kms as kms,
)
import aws_cdk as cdk
from constructs import Construct
from cdk_nag import NagSuppressions

class PipelineCDKStack(Stack):
    def __init__(self, scope: Construct, id: str, context: dict, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        ########### Global context ##################
        global_context = context["env"]
        trigger_on_push = global_context["environment"] != "prod"

        ########### Codepipeline context ##################
        codepipeline_context = context["cdk"]

        NagSuppressions.add_stack_suppressions(self, [
            {
                'id': 'AwsSolutions-S10',
                'reason': 'The S3 Bucket or bucket policy does not require requests to use SSL',
            },
        ])
        
        
        artifact_cdk_bucket = s3.Bucket(self, "ArtifactBucket",
            bucket_name=f"{global_context['prefix']}-{global_context['environment']}-cdk-codepipeline",
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
            actions=["*"],
            resources=["*"]
        ))
        


        # ########### CodePipeline ################
        pipeline = codepipeline.Pipeline(self, "Pipeline",
            pipeline_name=f"{global_context['prefix']}-{global_context['environment']}-{codepipeline_context['name']}-Pipeline",
            artifact_bucket=artifact_cdk_bucket
        )

        source_output = codepipeline.Artifact("SourceArtifact")
        
        source_action = actions.CodeStarConnectionsSourceAction(
            action_name="Github_Source",
            owner=codepipeline_context['owner'],
            repo=codepipeline_context['repo'],
            branch=codepipeline_context['branch'],
            connection_arn=codepipeline_context['connectionArn'],
            output=source_output,
            trigger_on_push=trigger_on_push
        )

        pipeline.add_stage(
            stage_name="Source",
            actions=[source_action]
        )

        # ############### CodeBuild ###############
        
        kms_key = kms.Key(self, "CDKBuildProjectKey",
                  alias="alias/codebuild/cdkbuildprojectkey",
                  enable_key_rotation=True)
        
        
        deploy_project = codebuild.PipelineProject(self, "CDKBuildProject",
            project_name=f"cdk-build-{global_context['environment']}",
            build_spec=codebuild.BuildSpec.from_source_filename("buildspec.yaml"),
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.from_code_build_image_id("aws/codebuild/standard:7.0"),
                environment_variables={
                    "CONTXT_ENV": codebuild.BuildEnvironmentVariable(
                        type=codebuild.BuildEnvironmentVariableType.PLAINTEXT,
                        value=f"{global_context['environment']}"
                    ),
                },
            ),
            role=build_role,
            encryption_key=kms_key
        )

        deploy_action = actions.CodeBuildAction(
            action_name="Deploy",
            project=deploy_project,
            input=source_output
        )

        pipeline.add_stage(
            stage_name="Deploy",
            actions=[deploy_action]
        )
