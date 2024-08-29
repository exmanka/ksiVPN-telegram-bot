pipeline {
    agent any
    environment {
        POSTGRES_PASSWORD = credentials('postgres-password')
        ADMIN_ID = credentials('admin-id')
        BOT_TOKEN = credentials('bot-token')
        YOOMONEY_TOKEN = credentials('yoomoney-token')
        YOOMONEY_ACCOUNT_NUMBER = credentials('yoomoney-account-number')
    }

    stages {
        stage('Build') {
            steps {
                echo $POSTGRES_PASSWORD
                echo $ADMIN_ID
                // sh printenv BOT_TOKEN
                // sh printenv YOOMONEY_TOKEN
                // sh printenv YOOMONEY_ACCOUNT_NUMBER
                echo 'Building..'
            }
        }
        stage('Test') {
            steps {
                echo 'Testing..'
            }
        }
        stage('Deploy') {
            steps {
                echo 'Deploying....'
            }
        }
    }
}