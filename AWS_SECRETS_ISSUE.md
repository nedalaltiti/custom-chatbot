# AWS Secrets Manager Configuration Issue

## The Problem

You're getting this error when running the bot:
```
AccessDeniedException: User: arn:aws:iam::794038237159:user/nedal.a is not authorized to perform: secretsmanager:GetSecretValue on resource: chatbot-clarity-db-local-postgres
```

## Why This Happens

1. **Wrong Secret Name**: Your `.env` file is trying to access `chatbot-clarity-db-local-postgres`, but the actual secret name in AWS is `chatbot-clarity-db-dev-postgres`

2. **No AWS Permissions**: Your IAM user `nedal.a` doesn't have permission to access AWS Secrets Manager

## How to Fix It

### Option 1: Fix Your .env File (Recommended for AWS Testing)

Update your `.env` file to use the correct secret names:

```bash
# Enable AWS Secrets Manager
USE_AWS_SECRETS=true
AWS_REGION=us-west-1

# Your existing AWS credentials 
AWS_ACCESS_KEY_ID=AKTA3RYC567TXBK463US
AWS_SECRET_ACCESS_KEY=pB8G/141LiPgruIZWytqOFkZXOECOtwS9T7aBu

# CORRECT secret names (change these!)
AWS_DB_SECRET_NAME=chatbot-clarity-db-dev-postgres
AWS_GEMINI_SECRET_NAME=genai-gemini-vertex-prod-api
```

### Option 2: Get AWS Permissions

Ask your DevOps team to add these permissions to your IAM user:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "secretsmanager:GetSecretValue"
            ],
            "Resource": [
                "arn:aws:secretsmanager:us-west-1:*:secret:chatbot-clarity-db-dev-postgres*",
                "arn:aws:secretsmanager:us-west-1:*:secret:genai-gemini-vertex-prod-api*"
            ]
        }
    ]
}
```

### Option 3: Test Without AWS (For Local Development)

For local testing and Docker testing, use this in your `.env`:

```bash
# Disable AWS Secrets Manager for local testing
USE_AWS_SECRETS=false
SKIP_DB_INIT=true
DISABLE_DB_WRITES=true

# Use your existing Google credentials
GOOGLE_APPLICATION_CREDENTIALS=./gemini-deployment-fe9ea6bb8c92.json
GOOGLE_CLOUD_PROJECT=gemini-deployment

# Copy your Teams credentials from your current .env
MICROSOFT_APP_ID=your-existing-app-id
MICROSOFT_APP_PASSWORD=your-existing-password
# ... etc
```

## For Docker Testing

To test the Docker image without AWS issues, run:

```bash
./test_docker_deployment.sh
```

This script will:
- Build the Docker image
- Run it with AWS disabled
- Test the health endpoints
- Show you how to package it for DevOps

## For Production Deployment

1. Use the `production.env.template` file
2. Fill in the Microsoft Teams credentials from Azure Portal
3. Make sure the deployment environment has AWS IAM credentials with Secrets Manager access
4. Use the correct secret names:
   - `chatbot-clarity-db-dev-postgres`
   - `genai-gemini-vertex-prod-api`

## Verification

After fixing the configuration, you should see:
```bash
INFO: Database connection established successfully
INFO: Gemini credentials loaded from AWS Secrets Manager
```

Instead of the access denied errors. 