pipeline {
    agent any
    options {
        disableConcurrentBuilds(abortPrevious: true)
    }

    stages {
        stage('Build') {
            environment {
                CONTAINER_REGISTRY_URL = 'https://index.docker.io/v1/'
                CONTAINER_REGISTRY_CREDS = credentials('dockerhub-creds')
                CONTAINER_REGISTRY_JSON = credentials('dockerhub-json')
            }
            failFast true
            parallel {
                stage('Build ksivpn-tgbot') {
                    agent {
                        docker {
                            label 'russia_moscow-maria && shell'
                            image 'gcr.io/kaniko-project/executor:v1.14.0-debug'
                            args '--entrypoint="" -v ${CONTAINER_REGISTRY_JSON}:/kaniko/.docker/config.json -u 0:1001'
                        }
                    }
                    environment {
                        PARALLEL_IMAGE_NAME = 'exmanka/ksivpn-telegram-bot'
                        PARALLEL_CACHE_REPO = 'exmanka/cache'
                        PARALLEL_DOCKERFILE = 'build/bot/Dockerfile'
                        PARALLEL_CONTEXT = "${WORKSPACE}"
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
                            --cache=true \
                            --cache-repo=${PARALLEL_CACHE_REPO}
                        '''
                    }
                }
                stage('Build ksivpn-tgbot-postgres') {
                    agent {
                        docker {
                            label 'russia_moscow-maria && shell'
                            image 'gcr.io/kaniko-project/executor:v1.14.0-debug'
                            args '--entrypoint="" -v ${CONTAINER_REGISTRY_JSON}:/kaniko/.docker/config.json -u 0:1001'
                        }
                    }
                    environment {
                        PARALLEL_IMAGE_NAME = 'exmanka/ksivpn-telegram-bot-postgres'
                        PARALLEL_CACHE_REPO = 'exmanka/cache'
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
                            --cache=true \
                            --cache-repo=${PARALLEL_CACHE_REPO}
                        '''
                    }
                }
            }
            post {
                always {
                    sh 'ls -al'
                    sh 'rm -rf /kaniko/.docker/config.json'
                }
            }
        }

        stage('Deploy:Dev') {
            environment {
                CONTAINER_REGISTRY_CREDS = credentials('dockerhub-creds')
                HOME = "$WORKSPACE"

                TZ = 'Europe/Moscow'
                POSTGRES_CREDS = credentials('postgres-creds')
                POSTGRES_USER = "${POSTGRES_CREDS_USR}"
                POSTGRES_PASSWORD = "${POSTGRES_CREDS_PSW}"
                POSTGRES_DB = credentials('postgres-db')
                POSTGRES_INITDB_ARGS = '--locale=en_US.UTF-8 --lc-time=ru_RU.UTF-8'
                ADDITIONAL_LANGUAGE = 'ru_RU'
                ADMIN_ID = credentials('admin-id')
                BOT_TOKEN = credentials('bot-token')
                YOOMONEY_TOKEN = credentials('yoomoney-token')
                YOOMONEY_ACCOUNT_NUMBER = credentials('yoomoney-account-number')
                BACKUP_PATH = credentials('backup-path')
                LOCALIZATION_LANGUAGE = 'ru'
                BOT_HTTP_PORT = credentials('port-bot-http')
                BOT_HTTPS_PORT = credentials('port-bot-https')
                POSTGRES_PORT = credentials('port-postgres')
                TAG = 'latest'
            }
            steps {
                sh 'echo $CONTAINER_REGISTRY_CREDS_PSW | docker login -u $CONTAINER_REGISTRY_CREDS_USR --password-stdin'
                sh 'docker compose down -v'
                sh 'docker compose up --pull always --quiet-pull -d'
                sh 'docker compose --ansi=always logs -f'
            }
        }
        stage('Deploy:Test') {
            steps {
                echo 'Deploying....'
            }
        }
    }
}