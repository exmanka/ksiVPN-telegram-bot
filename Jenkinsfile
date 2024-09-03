pipeline {
    agent any
    environment {
        POSTGRES_PASSWORD = credentials('postgres-password')
        ADMIN_ID = credentials('admin-id')
        BOT_TOKEN = credentials('bot-token')
        YOOMONEY_TOKEN = credentials('yoomoney-token')
        YOOMONEY_ACCOUNT_NUMBER = credentials('yoomoney-account-number')
        CONTAINER_REGISTRY_URL = 'https://index.docker.io/v1/'
        CONTAINER_REGISTRY_CREDS = credentials('dockerhub-creds')
        CONTAINER_REGISTRY_JSON = credentials('dockerhub-json')
    }

    stages {
        stage('Build') {
            failFast true
            parallel {
                stage('Build tgbot') {
                    agent {
                        docker {
                            image 'gcr.io/kaniko-project/executor:debug-v0.15.0'
                            args '--entrypoint="" -v ${CONTAINER_REGISTRY_JSON}:/kaniko/.docker/config.json'
                        }
                    }
                    environment {
                        PARALLEL_IMAGE_NAME = 'exmanka/ksivpn-telegram-bot'
                        PARALLEL_DOCKERFILE = 'build/bot/Dockerfile'
                        PARALLEL_CONTEXT = "${WORKSPACE}"
                        PARALLEL_TAG = 'latest'
                    }
                    steps {
                        sh 'cat /kaniko/.docker/config.json'
                        sh '''
                            . ${WORKSPACE}/.env
                            /kaniko/executor \
                            --context ${PARALLEL_CONTEXT} \
                            --dockerfile ${WORKSPACE}/${PARALLEL_DOCKERFILE} \
                            --destination ${PARALLEL_IMAGE_NAME}:${PARALLEL_TAG} \
                            --build-arg ADDITIONAL_LANGUAGE=${ADDITIONAL_LANGUAGE} \
                            --cache=true
                        '''
                    }
                }
                stage('Build tgbot-postgres') {
                    agent {
                        docker {
                            image 'gcr.io/kaniko-project/executor:debug-v0.15.0'
                            args '--entrypoint="" -v ${CONTAINER_REGISTRY_JSON}:/kaniko/.docker/config.json'
                        }
                    }
                    environment {
                        PARALLEL_IMAGE_NAME = 'exmanka/ksivpn-telegram-bot-postgres'
                        PARALLEL_DOCKERFILE = 'build/database/Dockerfile'
                        PARALLEL_CONTEXT = "${WORKSPACE}/build/database"
                        PARALLEL_TAG = 'latest'
                    }
                    steps {
                        sh '''
                            . ${WORKSPACE}/.env
                            /kaniko/executor \
                            --context ${PARALLEL_CONTEXT} \
                            --dockerfile ${WORKSPACE}/${PARALLEL_DOCKERFILE} \
                            --destination ${PARALLEL_IMAGE_NAME}:${PARALLEL_TAG} \
                            --build-arg ADDITIONAL_LANGUAGE=${ADDITIONAL_LANGUAGE} \
                            --cache=true
                        '''
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