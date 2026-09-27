# Backend deployment on ECS Fargate

This guide records the current demo deployment and the files needed to recreate
the backend task. The frontend stays local. AWS resources are in `us-east-1`.
The ECS task calls the existing PostgreSQL EC2 instance, the existing private S3
bucket, and Amazon Bedrock using its task role.

## Current layout

```text
Browser / local frontend
        |
Public ALB (HTTPS)
        |
ECS Fargate task, public subnet + public IP (port 8000)
        |                  |                 |
PostgreSQL EC2       Private S3 bucket    Bedrock
same VPC             task IAM role        task IAM role
```

The app runs as one Fargate task (`256` CPU units, `1024` MiB). The ALB is the
only network source allowed to reach task port 8000. The task security group is
the only source allowed to reach database port 5432. PostgreSQL currently sits
in a **public subnet** and has a public IPv4 address, but its security group
does not allow PostgreSQL from the internet. This is network-filtered, but it
is not the same as placing the database in a private subnet. SSH is restricted
to an operator `/32`; update that rule if the operator address changes.

The task uses no NAT Gateway. It receives a public IP so it can reach ECR,
CloudWatch Logs, Secrets Manager, S3, and Bedrock. This avoids a NAT Gateway's
hourly and data-processing charges. The public ALB terminates HTTPS and forwards
HTTP to the task within the VPC. The frontend is not deployed by this setup.

## Checked-in artifacts

- `task-definition.template.json` — current Fargate task settings. Replace its
  `${...}` placeholders when registering a new revision.
- `iam/ecs-tasks-trust-policy.json` — trust relationship for ECS task roles;
  the renderer fills in its account and region placeholders.
- `iam/task-role-policy.json` — application permissions for the configured S3
  object prefix and Bedrock models.
- `iam/execution-role-policy.template.json` — image pull, log write, and
  runtime-secret read permissions for the ECS agent.
- `render.py` — fills in account, region, image, and secret ARN placeholders in
  `/tmp/document-qa-deployment/` and verifies that the output is valid JSON.
- `resources.json` — identifiers and names for the currently running demo.

These are deployment inputs and an inventory, not a complete infrastructure-as-
code stack. The VPC, security groups, EC2 database, S3 bucket, ECR repository,
ALB, certificate, DNS, log group, and ECS service already exist. No AWS
resources are created by reading or validating these files.

## Before a deployment

Use an AWS identity authorized for this account and region. Do not put AWS access
keys in the task definition or application environment. The local CLI may use
the `work-bedrock` profile; ECS uses the task and execution roles in AWS.

The `document-qa/runtime` Secrets Manager secret must contain JSON keys named
`DATABASE_URL` and `JWT_SECRET`. The database URL must point to PostgreSQL on the
EC2 instance over its **private** VPC address, use the `psycopg` SQLAlchemy
scheme, and have URL-encoded credentials where needed. Generate a fresh JWT
secret locally, for example with:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Put these values into Secrets Manager using its console or another approved
secret-entry method. Never place the values in this repository, shell command
arguments, task-definition JSON, or screenshots. The container receives them as
environment variables when ECS starts it.

The EC2 security group must allow TCP 5432 from the ECS task security group only.
The task security group must allow TCP 8000 from the ALB security group only.
Do not open PostgreSQL or the task port to `0.0.0.0/0`. The task role policy
assumes the S3 bucket and model IDs listed in the example files.

## Build and push the backend image

Run from the repository root with Docker available and AWS CLI authenticated.
The image is built for the Fargate task's `X86_64` architecture.

```bash
export AWS_REGION=us-east-1
export AWS_ACCOUNT_ID="$(aws sts get-caller-identity --profile work-bedrock --query Account --output text)"
export ECR_REPOSITORY=document-qa-api
export IMAGE_TAG="demo-$(date -u +%Y%m%d%H%M%S)"
export IMAGE_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}:${IMAGE_TAG}"

aws ecr get-login-password --region "$AWS_REGION" --profile work-bedrock \
  | docker login --username AWS --password-stdin \
    "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
docker buildx build --platform linux/amd64 --push \
  -t "$IMAGE_URI" ./backend
```

The current ECR repository is `document-qa-api`. Image pushes are separate from
Bedrock inference; this build does not call a model.

## Render artifacts and configure IAM

The task definition and execution policy are templates so the repository does
not contain account-specific secret ARNs or image tags. Render them to `/tmp`,
not into the repository:

```bash
export RUNTIME_SECRET_ARN="$(aws secretsmanager describe-secret \
  --secret-id document-qa/runtime --region "$AWS_REGION" \
  --profile work-bedrock --query ARN --output text)"

python3 deployment/render.py
```

The ECS execution role and application task role are separate. Both use the
rendered ECS trust policy. If creating roles from scratch, run:

```bash
aws iam create-role --role-name document-qa-task \
  --profile work-bedrock \
  --assume-role-policy-document \
  file:///tmp/document-qa-deployment/iam/ecs-tasks-trust-policy.json
aws iam put-role-policy --role-name document-qa-task \
  --policy-name document-qa-task-policy \
  --profile work-bedrock \
  --policy-document file://deployment/iam/task-role-policy.json

aws iam create-role --role-name document-qa-execution \
  --profile work-bedrock \
  --assume-role-policy-document \
  file:///tmp/document-qa-deployment/iam/ecs-tasks-trust-policy.json
aws iam put-role-policy --role-name document-qa-execution \
  --policy-name document-qa-execution-policy \
  --profile work-bedrock \
  --policy-document \
  file:///tmp/document-qa-deployment/iam/execution-role-policy.json
```

When the roles already exist, update them with the `put-role-policy` commands
only. IAM changes require an operator identity with IAM permissions; the
application does not make them. Keep rendered files under `/tmp` and do not
commit them.

## Register and deploy the task definition

Register the rendered task definition:

```bash
aws ecs register-task-definition \
  --cli-input-json \
  file:///tmp/document-qa-deployment/task-definition.json \
  --region "$AWS_REGION" --profile work-bedrock
```

Update the existing service to the newly registered revision after confirming
the rendered image URI and secret **references** (not secret values):

```bash
aws ecs update-service --cluster document-qa-demo --service api \
  --task-definition document-qa-api \
  --force-new-deployment --region "$AWS_REGION" --profile work-bedrock
aws ecs wait services-stable --cluster document-qa-demo --services api \
  --region "$AWS_REGION" --profile work-bedrock
```

The task definition sets one Fargate task and has a container health check for
`/health`. Check the service events and `/ecs/document-qa-api` CloudWatch log
group if the task does not become healthy. Verify the public endpoint with
`https://rag-demo.cwmgenai.com/health` and the API schema at
`https://rag-demo.cwmgenai.com/openapi.json`.

## IAM permissions

The ECS execution role is used by the ECS agent to pull the image, write logs,
and fetch the two Secrets Manager values. The application task role allows
`s3:PutObject` and `s3:DeleteObject` only below
`arn:aws:s3:::sample-pdf-bucket-01-09-206/users/*`; it does not grant bucket
listing or reads. It allows `bedrock:InvokeModel` only for the four configured
model IDs in `us-east-1`. Bedrock's `bedrock:Rerank` action currently requires
resource `*`, so that one permission is broader and is called out in the policy.
The app does not need AWS access keys.

The task definition's execution role can read only the runtime secret whose
ARN is supplied at render time. If a customer-managed KMS key is used for that
secret, grant the execution role the corresponding narrowly scoped decrypt
permission as well.

## Stop the demo and cost notes

The live demo has one-time EventBridge Scheduler actions to stop the ECS service
and database and remove the ALB. Check their state and execution time in
EventBridge Scheduler before relying on them; they are time-specific and do not
appear in this repository as reusable schedules. Stopping the service alone
does not remove every charge: a running EC2 instance, ALB, storage, public IPv4,
CloudWatch logs, data transfer, or Bedrock requests can still cost money. Review
the AWS console after the demo and delete resources that are no longer needed.

This arrangement avoids NAT Gateway charges, but it cannot guarantee a specific
three-day spend. Pricing varies by region, traffic, storage, and model usage.
Bedrock embedding, reranking, and generation calls are billable; normal API
health checks do not invoke Bedrock.

## Known deployment limits

- The PostgreSQL EC2 host is in a public subnet; its security group is the
  control restricting database access. Moving it to private subnets would be a
  separate network change.
- There is one application task and no autoscaling, worker, or high-availability
  setup. This is a small demo deployment.
- The security groups, ALB, certificate, DNS, EC2 database, bucket, and scheduler
  schedules are not recreated by the checked-in artifacts.
- Database backups, rotation for the runtime secret, and a full restore
  procedure are not configured by this deployment guide.
