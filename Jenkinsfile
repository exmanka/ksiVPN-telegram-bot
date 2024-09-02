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
            matrix {
                agent {
                    docker {
                        image 'gcr.io/kaniko-project/executor:v1.14.0-debug'
                        args '--entrypoint=""'
                    }
                }
                axes {
                    axis {
                        name 'MATRIX_IMAGE_NAME'
                        values 'tgbot', 'tgbot-postgres'
                    }
                    axis {
                        name 'MATRIX_DOCKERFILE'
                        values 'build/bot/Dockerfile', 'build/database/Dockerfile'
                    }
                    // axis {
                    //     name 'MATRIX_CONTEXT'
                    //     values '${WORKSPACE}', '${WORKSPACE}/build/database'
                    // }
                }
                excludes {
                    exclude {
                        axis {

                        }
                    }
                }
                stages {
                    stage('Build ${MATRIX_IMAGE_NAME}') {
                        steps {
                            sh 'echo $MATRIX_IMAGE_NAME'
                            sh 'echo $MATRIX_DOCKERFILE'
                            // sh 'echo $MATRIX_CONTEXT'
                        }
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