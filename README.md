# aws

AWS設定ファイル置き場

## Organizations

Organizationsの設定は手動でポチポチやるしかない．

https://besolab.com/2020/04/22/aws-multi-account-strategy/#%E3%83%9E%E3%83%AB%E3%83%81%E3%82%A2%E3%82%AB%E3%82%A6%E3%83%B3%E3%83%88%E6%A7%8B%E6%88%90-organizations

SCP設定

```sh
cat scp/guardrails-for-core.json | jq -c > scp/comp_guardrails-for-core.json
aws organizations create-policy --content file://scp/comp_guardrails-for-core.json --name GuardrailsCore --type SERVICE_CONTROL_POLICY --description "Guardrails for core"

cat scp/guardrails-for-custom.json | jq -c > scp/comp_guardrails-for-custom.json
aws organizations create-policy --content file://scp/comp_guardrails-for-custom.json --name GuardrailsCustom --type SERVICE_CONTROL_POLICY --description "Guardrails for custom"

aws organizations create-policy --content file://scp/deny-all-outside-jp.json --name DenyAllOutsideJP --type SERVICE_CONTROL_POLICY --description "Deny access to outside Tokyo region"
aws organizations create-policy --content file://scp/deny-public-access.json --name DenyPublicAccess --type SERVICE_CONTROL_POLICY --description "Deny public access"

```

アカウント構成(カッコ内は適用したポリシー)

* Root
  * Core(GuardrailsCore, FullAWSAccess)
    * master
    * audit
    * log
  * Custom(GuardrailsCustom, DenyAllOutsideJP, FullAWSAccess)
    * Public
      * dev_a
      * dev_b
      * ...
    * Private(DenyPublicAccess)
      * dev_x
      * dev_y
      * ...

## SSO

こっちも手動でポチポチやるしかない．

https://besolab.com/2020/04/22/aws-multi-account-strategy/#%E3%83%A6%E3%83%BC%E3%82%B5%E3%82%99%E3%82%A2%E3%82%AB%E3%82%A6%E3%83%B3%E3%83%88%E7%AE%A1%E7%90%86-single-sign-on

## Master Account

MasterアカウントのCFnでStackSets実行用AdministrationRoleを作成する．

* テンプレートソース: Amazon S3 URL
* Amazon S3 URL: https://s3.amazonaws.com/cloudformation-stackset-templates-us-east-1/master_account_role.template
* スタックの名前: common-role-cfn-admin

## Log Account

LogアカウントのCFnでStackSets受入用ExecutionRoleを作成する．

* テンプレートソース: Amazon S3 URL
* Amazon S3 URL: https://s3.amazonaws.com/cloudformation-stackset-templates-us-east-1/managed_account_role.template
* スタックの名前: common-role-cfn-execute
* パラメータ
  * MasterAccountId: MasterのアカウントIDを指定

MasterアカウントのCredentialを設定して以下を実行する．

```sh
REGIONS='["ap-northeast-1"]'
LOG_ACCOUNT=`aws organizations list-accounts | jq '.Accounts[] | select(.Name == "log") | .Id'`
ORG_ID=`aws organizations describe-organization | jq ".Organization.Id"`

aws cloudformation create-stack-set --stack-set-name AWSOrganizations-LoggingResource --template-body file://cfn/log/logging-resource.yml \
  --parameters "ParameterKey=AWSLogsS3KeyPrefix,ParameterValue=${ORG_ID}"

aws cloudformation create-stack-instances --stack-set-name AWSOrganizations-LoggingResource --accounts "[${LOG_ACCOUNT}]" --regions ${REGIONS}
```

`AWSOrganizations-LoggingResource`でロードバランサと内部プロキシ用のファイル置き場もついでに作っているので不要であれば削除すること．

## Make StackSets

Targetアカウント用のStackSetsを作成する．
先程作成したS3バケット名が必要になるので，LogアカウントのCredentialを設定して以下のコマンドを実行しておくこと．

```sh
AUDIT_BUCKET=`aws s3api list-buckets | jq '.Buckets[] | select(.Name | startswith("aws-organizations-logs-")) | .Name'`
```

MasterアカウントのCredentialを設定して以下を実行する．

```sh
ORG_ID=`aws organizations describe-organization | jq ".Organization.Id"`
AUDIT_ACCOUNT=`aws organizations list-accounts | jq '.Accounts[] | select(.Name == "audit") | .Id'`

aws cloudformation create-stack-set --stack-set-name AWSOrganizations-BASE-ServiceRole --template-body file://cfn/target/service-role.yml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameters "ParameterKey=SecurityAccountId,ParameterValue=${AUDIT_ACCOUNT}"

aws cloudformation create-stack-set --stack-set-name AWSOrganizations-BASE-EnableConfig --template-body file://cfn/target/enable-config.yml \
  --parameters \
    "ParameterKey=SecurityAccountId,ParameterValue=${AUDIT_ACCOUNT}" \
    "ParameterKey=AWSLogsS3KeyPrefix,ParameterValue=${ORG_ID}" \
    "ParameterKey=AuditBucketName,ParameterValue=${AUDIT_BUCKET}"

aws cloudformation create-stack-set --stack-set-name AWSOrganizations-BASE-EnableCloudtrail --template-body file://cfn/target/enable-cloudtrail.yml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameters \
    "ParameterKey=SecurityAccountId,ParameterValue=${AUDIT_ACCOUNT}" \
    "ParameterKey=AWSLogsS3KeyPrefix,ParameterValue=${ORG_ID}" \
    "ParameterKey=AuditBucketName,ParameterValue=${AUDIT_BUCKET}"

aws cloudformation create-stack-set --stack-set-name AWSOrganizations-BASE-ForwardCloudwatch --template-body file://cfn/target/forward-cloudwatch.yml \
  --parameters "ParameterKey=SecurityAccountId,ParameterValue=${AUDIT_ACCOUNT}"

aws cloudformation create-stack-set --stack-set-name AWSOrganizations-BASE-EnableConfigRule --template-body file://cfn/target/enable-config-rule.yml \
  --parameters "ParameterKey=SecurityAccountId,ParameterValue=${AUDIT_ACCOUNT}"

aws cloudformation create-stack-set --stack-set-name AWSOrganizations-BASE-AwsLogsCloudwatch --template-body file://cfn/target/awslogs-cloudwatch.yml

aws cloudformation create-stack-set --stack-set-name AWSOrganizations-BASE-EnableSSMInventory --template-body file://cfn/target/enable-ssm-inventory.yml

aws cloudformation create-stack-set --stack-set-name AWSOrganizations-BASE-EnableSSMPatch --template-body file://cfn/target/enable-ssm-patch.yml

aws cloudformation create-stack-set --stack-set-name AWSOrganizations-BASE-EnableSSMInspec --template-body file://cfn/target/enable-ssm-inspec.yml \
  --capabilities CAPABILITY_NAMED_IAM

aws cloudformation create-stack-set --stack-set-name AWSOrganizations-EnableGuardDuty-Master --template-body file://cfn/audit/enable-guardduty-master.yml

aws cloudformation create-stack-set --stack-set-name AWSOrganizations-EnableGuardDuty-Member --template-body file://cfn/audit/enable-guardduty-member.yml \
  --parameters "ParameterKey=SecurityAccountId,ParameterValue=${AUDIT_ACCOUNT}"
```

## Target Account

追加アカウントの設定を行う．
AuditアカウントとLogアカウントも実行すること．

CFnでStackSets受入用ExecutionRoleを作成する(Logアカウントはすでに作成しているので不要)．

* テンプレートソース: Amazon S3 URL
* Amazon S3 URL: https://s3.amazonaws.com/cloudformation-stackset-templates-us-east-1/managed_account_role.template
* スタックの名前: common-role-cfn-execute
* パラメータ
  * MasterAccountId: MasterのアカウントIDを指定

以降はMasterアカウントのStackSetsを使って各アカウントの設定を行っていく．
MasterアカウントのCredentialをSSOログイン後画面からひろって設定しておくこと．

まずターゲットアカウントを指定する．
決め打ちでも良いし，自動取得しても良い．

```sh
ACCOUNT="Account1 Account2"
ACCOUNT=`aws organizations list-accounts | jq -c '[.Accounts[] | select(.Name != "master") | .Id] | join(" ")'`
```

作成しているStackSetsにアカウントを追加していく．

```sh
REGIONS=ap-northeast-1

eval aws cloudformation create-stack-instances --stack-set-name AWSOrganizations-BASE-ServiceRole --accounts ${ACCOUNT} --regions ${REGIONS}
# すべて実施完了するまで待つ

eval aws cloudformation create-stack-instances --stack-set-name AWSOrganizations-BASE-EnableConfig --accounts ${ACCOUNT} --regions ${REGIONS}
# すべて実施完了するまで待つ

eval aws cloudformation create-stack-instances --stack-set-name AWSOrganizations-BASE-EnableCloudtrail --accounts ${ACCOUNT} --regions ${REGIONS}
eval aws cloudformation create-stack-instances --stack-set-name AWSOrganizations-BASE-ForwardCloudwatch --accounts ${ACCOUNT} --regions ${REGIONS}
eval aws cloudformation create-stack-instances --stack-set-name AWSOrganizations-BASE-AwsLogsCloudwatch --accounts ${ACCOUNT} --regions ${REGIONS}
eval aws cloudformation create-stack-instances --stack-set-name AWSOrganizations-BASE-EnableSSMInventory --accounts ${ACCOUNT} --regions ${REGIONS}
eval aws cloudformation create-stack-instances --stack-set-name AWSOrganizations-BASE-EnableSSMPatch --accounts ${ACCOUNT} --regions ${REGIONS}
eval aws cloudformation create-stack-instances --stack-set-name AWSOrganizations-BASE-EnableSSMInspec --accounts ${ACCOUNT} --regions ${REGIONS}
eval aws cloudformation create-stack-instances --stack-set-name AWSOrganizations-BASE-EnableConfigRule --accounts ${ACCOUNT} --regions ${REGIONS}
```

## Core Account

MasterアカウントのCredentialをSSOログイン後画面からひろって設定しておくこと．

最初はAudit

```sh
EMAIL=your-email@address

REGIONS='["ap-northeast-1"]'
ORG_ID=`aws organizations describe-organization | jq ".Organization.Id"`
AUDIT_ACCOUNT=`aws organizations list-accounts | jq '.Accounts[] | select(.Name == "audit") | .Id'`

aws cloudformation create-stack-set --stack-set-name AWSOrganizations-SecurityTopic --template-body file://cfn/audit/security-topic.yml \
  --parameters \
    ParameterKey=AllConfigurationEmail,ParameterValue=${EMAIL} \
    ParameterKey=SecurityNotificationEmail,ParameterValue=${EMAIL} \
    ParameterKey=OrgID,ParameterValue=${ORG_ID}

aws cloudformation create-stack-instances --stack-set-name AWSOrganizations-SecurityTopic --accounts "[${AUDIT_ACCOUNT}]" --regions ${REGIONS}

TARGET_ACCOUNTS=`aws organizations list-accounts | jq '[.Accounts[] | select(.Name != "master" and .Name != "audit" and .Name != "log") | .Id] | join(",")'`

aws cloudformation create-stack-set --stack-set-name AWSOrganizations-SecurityResource --template-body file://cfn/audit/security-resource.yml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameters "ParameterKey=Accounts,ParameterValue=${TARGET_ACCOUNTS}"

aws cloudformation create-stack-instances --stack-set-name AWSOrganizations-SecurityResource --accounts "[${AUDIT_ACCOUNT}]" --regions ${REGIONS}
```

アカウントを追加した場合はAWSOrganizations-SecurityResourceを更新すること．

```sh
AUDIT_ACCOUNT=`aws organizations list-accounts | jq '.Accounts[] | select(.Name == "audit") | .Id'`
TARGET_ACCOUNT=`aws organizations list-accounts | jq '[.Accounts[] | select(.Name != "master") | .Id] | join(",")'`

aws cloudformation update-stack-set --stack-set-name AWSOrganizations-SecurityResource \
  --use-previous-template \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameters "ParameterKey=Accounts,ParameterValue=${TARGET_ACCOUNT}"
```

## GuardDuty

1. MasterアカウントのGuardDutyダッシュボードに移動し，`今すぐ始める`を選択
2. `委任された管理者`にAuditアカウントIDを入力し，`委任`を選択
3. AuditアカウントのGuardDutyダッシュボードに移動し，左のメニューの`設定 > アカウント`を選択
4. 画面上部に表示されている`このリージョンでOrganizationのGuardDutyを有効にする`から`有効化`を選択

以降はアカウントが追加されると自動でGuardDutyが働くようになる．

