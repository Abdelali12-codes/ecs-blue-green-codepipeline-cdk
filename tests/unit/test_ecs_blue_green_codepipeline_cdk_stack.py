import aws_cdk as core
import aws_cdk.assertions as assertions

from src.pipeline import EcsBlueGreenCodepipelineCdkStack

# example tests. To run these tests, uncomment this file along with the example
# resource in ecs_blue_green_codepipeline_cdk/ecs_blue_green_codepipeline_cdk_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = EcsBlueGreenCodepipelineCdkStack(app, "ecs-blue-green-codepipeline-cdk")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
