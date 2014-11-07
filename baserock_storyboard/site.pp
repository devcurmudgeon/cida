node default {
    class { 'storyboard':
        mysql_user_password => 'insecure',
        rabbitmq_user_password => 'insecure'
    }
}
