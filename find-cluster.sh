#!/bin/bash

# Helper script to find your EKS cluster name
# Run this with your AWS credentials that have EKS access

echo "🔍 Searching for EKS clusters in us-west-1..."

# Try to list clusters
echo "Attempting to list all clusters:"
aws eks list-clusters --region us-west-1 2>/dev/null || {
    echo "❌ No permission to list clusters with current credentials"
    echo ""
    echo "📝 Common cluster names to try:"
    echo "  - hrbot-cluster"
    echo "  - custom-chatbot-cluster" 
    echo "  - clarity-cluster"
    echo "  - dev-cluster"
    echo "  - prod-cluster"
    echo "  - staging-cluster"
    echo ""
    echo "🔧 How to test a cluster name:"
    echo "  aws eks describe-cluster --region us-west-1 --name CLUSTER_NAME"
    echo ""
    echo "📍 Or get it from AWS Console:"
    echo "  1. Login to AWS Console"
    echo "  2. Go to EKS service"
    echo "  3. Select us-west-1 region"
    echo "  4. Copy the cluster name you see"
    exit 1
}

echo ""
echo "✅ Found clusters! Copy one of the names above and update your pipeline."
echo ""
echo "🔧 Next steps:"
echo "1. Choose your cluster name from the list above"
echo "2. Replace 'your-eks-cluster-name' in bitbucket-pipelines.yml"
echo "3. Commit and push to trigger deployment" 