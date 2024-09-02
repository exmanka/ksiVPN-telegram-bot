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
                stage('Build tgbot') {
                    environment {
                        PARALLEL_IMAGE_NAME = 'tgbot'
                        PARALLEL_DOCKERFILE = 'build/bot/Dockerfile'
                        PARALLEL_CONTEXT = "${WORKSPACE}"
                    }
                    steps {
                        sh 'source ${WORKSPACE}/.env'
                        sh '''/kaniko/executor
                            --context ${MATRIX_CONTEXT}
                            --dockerfile ${WORKSPACE}/${MATRIX_DOCKERFILE}
                            --destination ${CI_REGISTRY_IMAGE}/${MATRIX_IMAGE_NAME}:${TAG}
                            --build-arg ADDITIONAL_LANGUAGE=${ADDITIONAL_LANGUAGE}
                            --cache=true'''
                    }
                }
                stage('Build tgbot-postgres') {
                    environment {
                        PARALLEL_IMAGE_NAME = 'tgbot-postgres'
                        PARALLEL_DOCKERFILE = 'build/database/Dockerfile'
                        PARALLEL_CONTEXT = "${WORKSPACE}/build/database"
                    }
                    steps {
                        sh 'source ${WORKSPACE}/.env'
                        sh '''/kaniko/executor
                            --context ${MATRIX_CONTEXT}
                            --dockerfile ${WORKSPACE}/${MATRIX_DOCKERFILE}
                            --destination ${CI_REGISTRY_IMAGE}/${MATRIX_IMAGE_NAME}:${TAG}
                            --build-arg ADDITIONAL_LANGUAGE=${ADDITIONAL_LANGUAGE}
                            --cache=true'''
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