Throwaway self-signed certificate for pin.test.

Used only by local HTTPS integration tests (TLS SNI and hostname
verification checks). It is not a secret, it is not trusted by any
system, and it must never be used outside these tests.

Regenerate (only if it expires) with:

    openssl req -x509 -newkey rsa:2048 -sha256 -nodes -days 3650 \\
      -keyout pin-test-key.pem -out pin-test-cert.pem \
      -subj "/CN=pin.test" \
      -addext "subjectAltName=DNS:pin.test" \
      -addext "basicConstraints=critical,CA:TRUE" \
      -addext "keyUsage=critical,keyCertSign,digitalSignature,keyEncipherment" \
      -addext "extendedKeyUsage=serverAuth"
