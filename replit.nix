{pkgs}: {
  deps = [
    pkgs.libxcrypt
    pkgs.libyaml
    pkgs.postgresql
    pkgs.openssl
  ];
}
