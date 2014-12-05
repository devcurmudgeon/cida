node default {
  group { 'ssl-cert':
    ensure => 'present'
  }

  # This directory doesn't seem to exist by default in Fedora
  file { '/etc/ssl/private':
    ensure => directory
    before => Class['storyboard::cert']
  }

  # TEMPORARY SSL private key
  openssl::certificate::x509 { 'storyboard_dummy':
    country => 'UK',
    organization => 'The Baserock Project',
    commonname => 'baserock.org',
    base_dir => '/tmp/',
    password => 'insecure',
    before => Class['storyboard::cert']
  }

  class { 'storyboard::cert':
    ssl_cert_file => '/tmp/storyboard_dummy.crt',
    ssl_key_file => '/tmp/storyboard_dummy.key',
    ssl_ca_file => '/etc/ssl/certs/ca-bundle.crt'
  }

  # need class storyboard::rabbitmq too

  class { 'storyboard::application':
    openid_url => 'http://openid.baserock.org/',

    mysql_host => '192.168.222.30',
    mysql_database => 'storyboard',
    mysql_user => 'storyboard',
    # FIXME: need to read this from a file in /var/lib
    mysql_user_password => 'storyboard_insecure',

    rabbitmq_host => 'localhost',
    rabbitmq_port => 5672,
    rabbitmq_vhost => '/',
    rabbitmq_user => 'storyboard',
    # FIXME: need to read this from a file in /var/lib
    rabbitmq_user_password => 'storyboard_insecure'
  }
}
