from aws_cdk import (
    # Duration,
    SecretValue,
    CfnDynamicReference,
    CfnDynamicReferenceService,
    Stack,
    # aws_sqs as sqs,
)
from aws_cdk import (aws_codebuild as codebuild,
                     aws_codecommit as codecommit,
                     aws_codepipeline as codepipeline,
                     aws_secretsmanager as secret,
                     aws_codedeploy as codedeploy,
                     aws_codepipeline_actions as codepipeline_actions,
                     aws_lambda as lambda_, aws_s3 as s3,
                     aws_iam as iam, aws_ecr as ecr)
from constructs import Construct
from .ecs_cluster import EcsCluster

class EcsBlueGreenCodepipelineCdkStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ECR
        ecr_repo = ecr.Repository.from_repository_name(self, "ecrrepo", repository_name="nginx-ecs")
        
        # ecs cluster
        ecs_cluster = EcsCluster(self, "ecscluster", ecr_repo=ecr_repo)

        # create code builds
        code_build = codebuild.PipelineProject(self, "build",
                        build_spec=codebuild.BuildSpec.from_source_filename("buildspec.yaml"),
                        environment=codebuild.BuildEnvironment(
                            build_image=codebuild.LinuxBuildImage.AMAZON_LINUX_2_3,
                            privileged=True),
                        environment_variables=self.get_build_env_vars(ecr_repo))
        
        self.add_role_access_to_build(code_build)
        
        # create codedeploy
        application = codedeploy.EcsApplication(self, "CodeDeployApplication",
                    application_name="MyApplication"
                )
        
        codedeploy_group = codedeploy.EcsDeploymentGroup(self, "BlueGreenDG",
            application= application,
            service=ecs_cluster.fargateService,
            blue_green_deployment_config=codedeploy.EcsBlueGreenDeploymentConfig(
                blue_target_group=ecs_cluster.blue_target,
                green_target_group=ecs_cluster.green_target,
                listener=ecs_cluster.httplistener
            ),
            deployment_config=codedeploy.EcsDeploymentConfig.CANARY_10_PERCENT_5_MINUTES
        )
        
        codedeploy_group.role.add_managed_policy(
              iam.ManagedPolicy.from_aws_managed_policy_name("AWSCodeDeployRoleForECS")
        )
        # create pipeline
        source_output = codepipeline.Artifact()
        build_output = codepipeline.Artifact("BuildOutput")

        codepipeline.Pipeline(
            self, "Pipeline",
            stages=[
                codepipeline.StageProps(stage_name="codecommit",
                      actions=[
                          codepipeline_actions.GitHubSourceAction(
                                oauth_token=SecretValue.cfn_dynamic_reference(
                                      CfnDynamicReference(CfnDynamicReferenceService.SECRETS_MANAGER, 
                                                    "github-access-token:SecretString:token")
                                ),
                                action_name="github",
                                owner="Abdelali12-codes",
                                branch="main",
                                repo="ecs-blue-green-backend",
                                output=source_output
                          )
                      ]                    
                    ),
                codepipeline.StageProps(stage_name="build",
                               actions= [
                                   codepipeline_actions.CodeBuildAction(
                                       action_name="codebuild",
                                       input= source_output,
                                       project= code_build,
                                       outputs=[
                                           build_output
                                       ]
                                   )
                               ]
                ),

                codepipeline.StageProps(stage_name="ecsdeploy",
                        actions=[
                        codepipeline_actions.CodeDeployEcsDeployAction(
                          action_name="codedeploy",
                          app_spec_template_file=codepipeline.ArtifactPath(
                              artifact=source_output,
                              file_name="appspec.yaml"
                          ),
                          task_definition_template_file=codepipeline.ArtifactPath(
                              artifact=source_output,
                              file_name="taskdef.json"
                          ),
                          container_image_inputs=[
                            codepipeline_actions.CodeDeployEcsContainerImageInput(
                                input=build_output,
                                # the properties below are optional
                                task_definition_placeholder="IMAGE_NAME"
                                              )
                            ],
                            deployment_group=codedeploy_group
                        )
                     ]
                )

            ]
        )
    def add_role_access_to_build(self, code_build: codebuild.PipelineProject):
            code_build.role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEC2ContainerRegistryFullAccess"))
            code_build.role.add_managed_policy(
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMReadOnlyAccess"))
            code_build.add_to_role_policy(iam.PolicyStatement(
                actions=["kms:Decrypt", "kms:GenerateDataKey*"], resources=["*"]))

    def get_build_env_vars(self, ecr_repo):
            return {
                        "ECR_REPO_URI": codebuild.BuildEnvironmentVariable(value=ecr_repo.repository_uri),
                        "AWS_DEFAULT_REGION": codebuild.BuildEnvironmentVariable(value=Stack.of(self).region),
                        "AWS_ACCOUNT_ID": codebuild.BuildEnvironmentVariable(value=Stack.of(self).account)
                    }