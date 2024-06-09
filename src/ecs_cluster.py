from constructs import Construct
import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_ecs as ecs
import aws_cdk.aws_iam as iam
import aws_cdk.aws_elasticloadbalancingv2 as elb
import aws_cdk.aws_certificatemanager as acm
import aws_cdk.aws_route53_targets as targets
import aws_cdk.aws_ecr as ecr
import aws_cdk.aws_route53 as route53
import aws_cdk.aws_elasticloadbalancingv2 as albv2
import os

DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
SUB_DIR = os.path.dirname(os.path.realpath(__file__))

class EcsCluster(Construct):

    def __init__(self, scope: Construct, construct_id: str, ecr_repo: ecr.Repository, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        self.vpc = ec2.Vpc(self, f"{id}-Vpc",
                      ip_addresses=ec2.IpAddresses.cidr("12.10.0.0/16"),
                      enable_dns_hostnames= True,
                      enable_dns_support=True,
                      max_azs=3,
                      subnet_configuration=[
                            ec2.SubnetConfiguration(
                                name = "public-subnet",
                                subnet_type = ec2.SubnetType.PUBLIC,
                                cidr_mask=24,
                            ),
                            ec2.SubnetConfiguration( 
                                name="isolated-subnet",
                                subnet_type= ec2.SubnetType.PRIVATE_ISOLATED,
                                cidr_mask=24
                            ),
                        ],
            )
       
       
    
        # Route53 record
        zone = route53.HostedZone.from_hosted_zone_attributes(self,'Route53HostedZone',
            hosted_zone_id="Z05045244G4M5OFGHB4C",
           zone_name="abdelalitraining.com"
        )
        
        # Acm Certificate
        certificate = acm.Certificate.from_certificate_arn(self, "domainCert", "arn:aws:acm:us-east-2:080266302756:certificate/2d38c49e-009a-46b1-8bc2-571eebf19586")
        
        # Loadbalancer sg
        alb_sg = ec2.SecurityGroup(self, "ALBSSG",
           vpc = self.vpc,
           security_group_name="alb-sg",
           allow_all_outbound=True,
        )
        
        alb_sg.add_ingress_rule(
            ec2.Peer.ipv4('0.0.0.0/0'),
            ec2.Port.tcp(80)
        )
        
        alb_sg.add_ingress_rule(
            ec2.Peer.ipv4('0.0.0.0/0'),
            ec2.Port.tcp(443)
        )
        # Application Loadbalancer
        alb = elb.ApplicationLoadBalancer(self, "AWSALBECS",
            vpc=self.vpc,
            internet_facing=True,
            load_balancer_name="ecs-blue-green-project",
            security_group= alb_sg,
            vpc_subnets=ec2.SubnetSelection(
                    subnet_type = ec2.SubnetType.PUBLIC
                ),
            
        )
        
        # Alias Record
        route53.ARecord(self, "AliasRecord",
            zone=zone,
            target=route53.RecordTarget.from_alias(targets.LoadBalancerTarget(alb)),
            record_name="nginx.abdelalitraining.com"
        )
        
        # ECS Cluster
        cluster = ecs.Cluster(self, "ecscluster",
                               vpc=self.vpc,
                               cluster_name="ecs-cluster"
                              )
            
        # task role and excecution role  
        taskrole = iam.Role(self, "Role",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            role_name="aws-ecs-task-role",
            managed_policies=[
                  iam.ManagedPolicy.from_aws_managed_policy_name("AWSXrayFullAccess"),
                  iam.ManagedPolicy.from_aws_managed_policy_name("AmazonPrometheusFullAccess"),
                ]
        )
        # taskexecutionRolePolicy = iam.PolicyStatement( 
        #     effect=iam.Effect.ALLOW,
        #     actions=[
        #         "ecr:getauthorizationtoken",
        #         "ecr:batchchecklayeravailability",
        #         "ecr:getdownloadurlforlayer",
        #         "ecr:batchgetimage",
        #         "logs:createlogstream",
        #         "logs:putlogevents"
        #     ],
        #     resources=["*"]
        # )

        taskexecutionrole = iam.Role.from_role_name(self, "taskexecutionrole", role_name="ecsTaskExecutionRole")
        
        # django ecs task definition
        apptaskDef = ecs.TaskDefinition(self, "nginxTaskDefinition",
              compatibility=ecs.Compatibility.FARGATE,
              family="ecs-codepipeline-task",
              network_mode=ecs.NetworkMode.AWS_VPC,
              task_role=taskrole,
              execution_role=taskexecutionrole,
              cpu="256",
              memory_mib="512"
        )
        
        #apptaskDef.add_to_execution_role_policy(taskexecutionRolePolicy)
        
        container = apptaskDef.add_container("nginxContainer",
              container_name="ecs-codepipeline-container",
              image=ecs.ContainerImage.from_ecr_repository(ecr_repo),
              memory_reservation_mib= 512,
              cpu= 256,
              port_mappings=[
                  ecs.PortMapping(
                      container_port=80,
                      protocol=ecs.Protocol.TCP
                  )
              ],
              logging= ecs.LogDriver.aws_logs(
                    stream_prefix="ecs-djangoapp"
                  )
            )
        
        # django application security group
        
        app_ecs_service_sg = ec2.SecurityGroup(self, "djangoServiceSG",
           vpc = self.vpc,
           security_group_name="nginx-ecs-service-sg",
           allow_all_outbound=True,
        )
        
        self.fargateService = ecs.FargateService(self,
                "nginxEcsService",
                service_name="nginx-service",
                cluster=cluster,
                assign_public_ip=True,
                enable_execute_command=True,
                security_groups= [app_ecs_service_sg],
                deployment_controller=ecs.DeploymentController(
                    type=ecs.DeploymentControllerType.CODE_DEPLOY
                ),
                task_definition=apptaskDef,
                vpc_subnets=ec2.SubnetSelection(
                    subnet_type = ec2.SubnetType.PUBLIC
                )
                
            )
        
        # target groups

        self.blue_target = albv2.ApplicationTargetGroup(
            self, "bluetarget", vpc=self.vpc,
            target_group_name="blue-target",
            target_type= albv2.TargetType.IP,
            port=80
        )

        self.green_target = albv2.ApplicationTargetGroup(
            self, "greentarget", vpc= self.vpc,
            target_group_name="green-target",
            target_type= albv2.TargetType.IP,
            port=80
        )

        self.fargateService.attach_to_application_target_group(self.blue_target)
            
        self.httplistener = alb.add_listener("AWSAlbListenerHttp",
          port=80,
          default_target_groups=[self.blue_target]
        )
        self.http8080listener = alb.add_listener("AWSAlbListenerHttp8000",
           port=8080,
           default_target_groups=[self.green_target]
        )
        
        # self.blue_target = self.httplistener.add_targets(
        #     "HttpTarget",
        #       port=80,
        #     )
        
        # self.green_target = self.http8080listener.add_targets("Http8080Target",
        #        port=80,
        #     )
