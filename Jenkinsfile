pipeline {
    agent any
    environment {
        POSTGRES_PASSWORD = credentials('postgres-password')
        ADMIN_ID = credentials('admin-id')
        BOT_TOKEN = credentials('bot-token')
        YOOMONEY_TOKEN = credentials('yoomoney-token')
        YOOMONEY_ACCOUNT_NUMBER = credentials('yoomoney-account-number')
        DOCKERHUB_CREDS = credentials('dockerhub-creds')
    }

    stages {
        stage('Build') {
            failFast true
            parallel {
                stage("Build ${MATRIX_IMAGE_NAME}") {
                    environment {
                        MATRIX_IMAGE_NAME = 'tgbot'
                        MATRIX_DOCKERFILE = 'build/bot/Dockerfile'
                        MATRIX_CONTEXT = "${WORKSPACE}"
                    }
                    steps {
                        sh 'echo $MATRIX_IMAGE_NAME'
                        sh 'echo $MATRIX_DOCKERFILE'
                        sh 'echo $MATRIX_CONTEXT'
                    }
                }
                stage("Build ${MATRIX_IMAGE_NAME}") {
                    environment {
                        MATRIX_IMAGE_NAME = 'tgbot-postgres'
                        MATRIX_DOCKERFILE = 'build/database/Dockerfile'
                        MATRIX_CONTEXT = "${WORKSPACE}/build/database"
                    }
                    steps {
                        sh 'echo $MATRIX_IMAGE_NAME'
                        sh 'echo $MATRIX_DOCKERFILE'
                        sh 'echo $MATRIX_CONTEXT'
                    }
                }
            }
        }

        // parallel {
        //     steps {
        //         sh 'pwd'
        //         sh 'ls -al'
        //         sh 'printenv'
        //         sh 'source ${WORKSPACE}/.env'
        //         sh '''/kaniko/executor
        //             --context ${MATRIX_CONTEXT}
        //             --dockerfile ${CI_PROJECT_DIR}/${MATRIX_DOCKERFILE}
        //             --destination ${CI_REGISTRY_IMAGE}/${MATRIX_IMAGE_NAME}:${TAG}
        //             --build-arg ADDITIONAL_LANGUAGE=${ADDITIONAL_LANGUAGE}
        //             --cache=true'''
        //     }
        // }

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