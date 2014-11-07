node default {
  group { 'ssl-cert':
    ensure => 'present'
  }

  # TEMPORARY SSL private key
  openssl::certificate::x509 { 'storyboard_dummy':
    country => 'UK',
    organization => 'The Baserock Project',
    commonname => 'baserock.org',
    base_dir => '/etc/ssl',
    password => 'insecure'
  } ->

  class { 'storyboard':
    mysql_user_password => 'insecure',
    rabbitmq_user_password => 'insecure',
    ssl_cert_file => '/etc/ssl/certs/storyboard_dummy.crt',
    ssl_key_file => '/etc/ssl/certs/storyboard_dummy.key',
    require => Group['ssl-cert']
  }
}
