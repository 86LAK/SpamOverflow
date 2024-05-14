terraform {
    required_providers {
        aws = {
            source  = "hashicorp/aws"
            version = "~> 5.0"
      }
      docker = {
        source  = "kreuzwerker/docker"
        version = "3.0.2"
      }
  }
}

provider "aws" {
    region = "us-east-1"
    shared_credentials_files = ["./credentials"]
}

locals {
  database_username = "administrator"
  database_password = "verySecretPassword" # this is bad. nah who says lmao : ) 
  image = "${aws_ecr_repository.spamOverflow.repository_url}:latest"
}



resource "local_file" "url" {
    content = "http://${aws_lb.spamOverflow.dns_name}:8080/api/v1/"
    filename = "./api.txt"
}



resource "aws_db_instance" "spamOverflow_database" {
  allocated_storage      = 20
  max_allocated_storage  = 1000
  engine                 = "postgres"
  engine_version         = "14"
  instance_class         = "db.t4g.medium" // TODO use larger one and see if my scalable app can then connect to it...
  db_name                = "spamOverflow_database"
  username               = local.database_username
  password               = local.database_password
  parameter_group_name   = "default.postgres14"
  skip_final_snapshot    = true
  vpc_security_group_ids = [aws_security_group.spamOverflow_database.id]
  publicly_accessible    = true

  tags = {
    Name = "spamOverflow_database"
  }
}


resource "aws_security_group" "spamOverflow_database" {
  name        = "spamOverflow_database"
  description = "Allow inbound Postgresql traffic"

  ingress {
    from_port        = 5432
    to_port          = 5432
    protocol         = "tcp"
    cidr_blocks      = ["0.0.0.0/0"]
  }

  egress {
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  tags = {
    Name = "spamOverflow_database"
  }
}



data "aws_iam_role" "lab" {
    name = "LabRole"
}

data "aws_vpc" "default" {
    default = true
}

data "aws_subnets" "private" {
    filter {
        name   = "vpc-id"
        values = [data.aws_vpc.default.id]
    }
}

resource "aws_ecs_cluster" "spamOverflow" {
    name = "spamOverflow"
}


resource "aws_ecs_task_definition" "spamOverflow" {
    family                   = "spamOverflow"
    network_mode             = "awsvpc"
    requires_compatibilities = ["FARGATE"]
    cpu                      = 4096  #TODO figure out 
    memory                   = 8192 #TODO figure out
    execution_role_arn       = data.aws_iam_role.lab.arn
  
    container_definitions = <<DEFINITION
  [
    {
      "image": "${local.image}",
      "cpu": 4096,
      "memory": 8192,
      "name": "spamOverflow",
      "networkMode": "awsvpc",
      "portMappings": [
        {
          "containerPort": 8080,
          "hostPort": 8080
        }
      ],
      "environment": [
        {
          "name": "SQLALCHEMY_DATABASE_URI",
          "value": "postgresql://${local.database_username}:${local.database_password}@${aws_db_instance.spamOverflow_database.address}:${aws_db_instance.spamOverflow_database.port}/${aws_db_instance.spamOverflow_database.db_name}"
        }, 
        {
          "name": "QUEUE_NAME",
          "value": "${aws_sqs_queue.low_priority_queue.name}"
        }, 
        {
          "name": "HIGH_PRIORITY_QUEUE",
          "value": "${aws_sqs_queue.high_priority_queue.name}"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/spamOverflow/spamOverflow",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs",
          "awslogs-create-group": "true"
        }
      }
    }
  ]
  DEFINITION
}


resource "aws_ecs_service" "spamOverflow" {
    name            = "spamOverflow"
    cluster         = aws_ecs_cluster.spamOverflow.id
    task_definition = aws_ecs_task_definition.spamOverflow.arn
    desired_count   = 1
    launch_type     = "FARGATE"
  
    network_configuration {
      subnets             = data.aws_subnets.private.ids
      security_groups     = [aws_security_group.spamOverflow.id]
      assign_public_ip    = true
    }
    load_balancer {
      target_group_arn = aws_lb_target_group.spamOverflow.arn
      container_name   = "spamOverflow"
      container_port   = 8080
  }
}

resource "aws_security_group" "spamOverflow" {
    name = "spamOverflow"
    description = "spamOverflow Security Group"
  
    ingress {
      from_port = 8080
      to_port = 8080
      protocol = "tcp"
      cidr_blocks = ["0.0.0.0/0"]
    }
  
    ingress {
      from_port = 22
      to_port = 22
      protocol = "tcp"
      cidr_blocks = ["0.0.0.0/0"]
    }
  
    egress {
      from_port = 0
      to_port = 0
      protocol = "-1"
      cidr_blocks = ["0.0.0.0/0"]
    }
}

### new wk5 stuff evan made for me <3
data "aws_ecr_authorization_token" "ecr_token" {}

provider "docker" {
  registry_auth {
    address  = data.aws_ecr_authorization_token.ecr_token.proxy_endpoint
    username = data.aws_ecr_authorization_token.ecr_token.user_name
    password = data.aws_ecr_authorization_token.ecr_token.password
  }
}

resource "aws_ecr_repository" "spamOverflow" {
  name = "spamoverflow"
}

resource "docker_image" "spamOverflow" {
  name         = "${aws_ecr_repository.spamOverflow.repository_url}:latest"
  build {
    context = "."
    dockerfile = "Dockerfile.app"
  }
}

resource "docker_registry_image" "spamOverflow" {
  name = docker_image.spamOverflow.name
}


## new wk5 stuff evan made for me <3 above.





############# everything below from wk6 prac shet
resource "aws_lb_target_group" "spamOverflow" {
  name          = "spamOverflow"
  port          = 8080
  protocol      = "HTTP"
  vpc_id        = aws_security_group.spamOverflow.vpc_id
  target_type   = "ip"

  health_check {
    path                = "/api/v1/health"
    port                = "8080"
    protocol            = "HTTP"
    healthy_threshold   = 2
    unhealthy_threshold = 10
    timeout             = 10
    interval            = 15 # 150 seconds before marked as unhealthy and spins next one
  }
}


resource "aws_lb" "spamOverflow" {
  name               = "spamOverflow"
  internal           = false
  load_balancer_type = "application"
  subnets            = data.aws_subnets.private.ids
  security_groups    = [aws_security_group.spamOverflow.id]
}


resource "aws_lb_listener" "spamOverflow" {
  load_balancer_arn   = aws_lb.spamOverflow.arn
  port                = "8080"
  protocol            = "HTTP"

  default_action {
    type              = "forward"
    target_group_arn  = aws_lb_target_group.spamOverflow.arn
  }
}



# below is wk6 and also contains autoscaling shit. below is the  section just above 4.3 of wk6.

##TODO uncomment all of below and test it works when my aaws spins back up and works

resource "aws_appautoscaling_target" "spamOverflow" {
  depends_on = [aws_ecs_service.spamOverflow] 
  max_capacity        = 1 #TODO
  min_capacity        = 1 #TODO 
  resource_id         = "service/spamOverflow/spamOverflow"
  scalable_dimension  = "ecs:service:DesiredCount"
  service_namespace   = "ecs"
}


resource "aws_appautoscaling_policy" "spamOverflow-cpu" {
  depends_on = [aws_ecs_service.spamOverflow] 
  name                = "spamOverflow-cpu"
  policy_type         = "TargetTrackingScaling"
  resource_id         = aws_appautoscaling_target.spamOverflow.resource_id
  scalable_dimension  = aws_appautoscaling_target.spamOverflow.scalable_dimension
  service_namespace   = aws_appautoscaling_target.spamOverflow.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type  = "ECSServiceAverageCPUUtilization"
    }

    target_value              = 86 #TODO play with this number for cpu utilisation
  }
}


# from queues wk8 i think. whichever week has queues in it. the ecs task defintion also passes this below as a environment variable
resource "aws_sqs_queue" "low_priority_queue" { 
 name = "low_priority_queue" 
} 

resource "aws_sqs_queue" "high_priority_queue" { 
 name = "high_priority_queue" 
} 

#####################################
# to get my homie the worker up and about and using his brain

resource "aws_ecr_repository" "spamworker" {
  name = "spamworker"
}


resource "docker_image" "spamworker" {
  name         = "${resource.aws_ecr_repository.spamworker.repository_url}:latest"
  build {
    context = "./path/to/your/worker"
    dockerfile = "Dockerfile.worker"
  }
}

resource "docker_registry_image" "spamworker" {
  name = docker_image.spamworker.name
}


resource "aws_ecs_task_definition" "spamworker" {
  family                   = "spamworker"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 4096 #TODO figure out 
  memory                   = 12288 #TODO figure out
  execution_role_arn       = data.aws_iam_role.lab.arn

  container_definitions = <<DEFINITION
  [
    {
      "image": "${docker_registry_image.spamworker.name}",
      "cpu": 4096,
      "memory": 12288,
      "name": "spamworker",
      "networkMode": "awsvpc",
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/spamOverflow/spamworker",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs",
          "awslogs-create-group": "true"
        }
      },
      "environment": [
        {
          "name": "DB_URL",
          "value": "postgresql://${local.database_username}:${local.database_password}@${aws_db_instance.spamOverflow_database.address}:${aws_db_instance.spamOverflow_database.port}/${aws_db_instance.spamOverflow_database.db_name}"
        },
        {
          "name": "QUEUE_NAME",
          "value": "${aws_sqs_queue.low_priority_queue.name}"
        }
      ]
    }
  ]
  DEFINITION
}


resource "aws_ecs_service" "spamworker" {
  name            = "spamworker"
  cluster         = aws_ecs_cluster.spamOverflow.id
  task_definition = aws_ecs_task_definition.spamworker.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets             = data.aws_subnets.private.ids
    security_groups     = [aws_security_group.spamOverflow.id]
    assign_public_ip    = true
  }
}





# to get my homie the worker up and about and using his brain
####################################




// high priority worker below with autoscaling
resource "aws_ecs_task_definition" "spamworker_high" {
  family                   = "spamworker_high"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 4096 #TODO figure out 
  memory                   = 12288 #TODO figure out
  execution_role_arn       = data.aws_iam_role.lab.arn

  container_definitions = <<DEFINITION
  [
    {
      "image": "${docker_registry_image.spamworker.name}",
      "cpu": 4096,
      "memory": 12288,
      "name": "spamworker_high",
      "networkMode": "awsvpc",
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/spamOverflow/spamworker_high",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs",
          "awslogs-create-group": "true"
        }
      },
      "environment": [
        {
          "name": "DB_URL",
          "value": "postgresql://${local.database_username}:${local.database_password}@${aws_db_instance.spamOverflow_database.address}:${aws_db_instance.spamOverflow_database.port}/${aws_db_instance.spamOverflow_database.db_name}"
        },
        {
          "name": "QUEUE_NAME",
          "value": "${aws_sqs_queue.high_priority_queue.name}"
        }
      ]
    }
  ]
  DEFINITION
}

resource "aws_ecs_service" "spamworker_high" {
  name            = "spamworker_high"
  cluster         = aws_ecs_cluster.spamOverflow.id
  task_definition = aws_ecs_task_definition.spamworker_high.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets             = data.aws_subnets.private.ids
    security_groups     = [aws_security_group.spamOverflow.id]
    assign_public_ip    = true
  }
}

resource "aws_appautoscaling_target" "spamworker_high" {
  max_capacity        = 4 #TODO check
  min_capacity        = 1
  resource_id         = "service/spamOverflow/spamworker_high"
  scalable_dimension  = "ecs:service:DesiredCount"
  service_namespace   = "ecs"
  depends_on = [aws_ecs_service.spamworker_high]
}

resource "aws_appautoscaling_policy" "spamworker_high-cpu" {
  name                = "spamworker_high-cpu"
  policy_type         = "TargetTrackingScaling"
  resource_id         = aws_appautoscaling_target.spamworker_high.resource_id
  scalable_dimension  = aws_appautoscaling_target.spamworker_high.scalable_dimension
  service_namespace   = aws_appautoscaling_target.spamworker_high.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type  = "ECSServiceAverageCPUUtilization"
    }

    target_value              = 20 # cpu util %
    scale_in_cooldown =  60 # 1min between scale down
    scale_out_cooldown = 60 # can scale up to help within 60 seconds...
  }
}


// high priority worker stuff above


// low priority worker autoscaing stuff
resource "aws_appautoscaling_target" "spamworker" {
  max_capacity        = 4 #TODO check
  min_capacity        = 1
  resource_id         = "service/spamOverflow/spamworker"
  scalable_dimension  = "ecs:service:DesiredCount"
  service_namespace   = "ecs"
  depends_on          = [aws_ecs_service.spamworker]
}

resource "aws_appautoscaling_policy" "spamworker-cpu" {
  name                = "spamworker-cpu"
  policy_type         = "TargetTrackingScaling"
  resource_id         = aws_appautoscaling_target.spamworker.resource_id
  scalable_dimension  = aws_appautoscaling_target.spamworker.scalable_dimension
  service_namespace   = aws_appautoscaling_target.spamworker.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type  = "ECSServiceAverageCPUUtilization"
    }

    target_value              = 20 # cpu util %
    scale_in_cooldown =  60 # 1min between scale down
    scale_out_cooldown = 60 # can scale up to help within 60 seconds...
  }
}

// low priority worker autoscalling stuff