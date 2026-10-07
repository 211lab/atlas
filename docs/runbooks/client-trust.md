# Client Trust for Atlas Root Certificate

This runbook details how to establish trust for the `atlas-ca` root certificate on various devices, enabling secure HTTPS access to services within the `*.atlas.lan` domain without browser warnings.

## 1. Get the certificate

The `atlas-ca` is a private root certificate authority used within the Atlas home lab. To trust services like `git.atlas.lan` or `argocd.atlas.lan`, you need to obtain this certificate and install it on your devices.

Download the public root certificate directly from this site:

- [atlas-ca.crt](../assets/atlas-ca.crt) (canonical URL: `https://docs.atlas.lan/assets/atlas-ca.crt`)

This is the public trust anchor only — it contains no signing key and is safe to
distribute.

Alternatively, if you have `kubectl` access to the cluster, you can extract it using the following command:

```sh
export PATH="$HOME/.local/bin:$PATH" KUBECONFIG=~/.kube/atlas-admin.yaml
kubectl -n cert-manager get secret atlas-ca-tls -o jsonpath='{.data.tls\.crt}' | base64 -d > atlas-ca.crt
```

It's a 550-byte PEM. You can verify its fingerprint (e.g., compare over a trusted channel) to ensure authenticity:

```sh
openssl x509 -in atlas-ca.crt -noout -fingerprint -sha256
# Expected: 28:9D:03:B1:1B:D1:E1:45:1C:0C:F7:DC:06:B8:E7:A4:82:8D:A1:D2:01:6B:2F:63:88:95:BE:B6:5F:78:64:AC
```

After obtaining the `atlas-ca.crt` file, copy it to the target device (e.g., via scp, USB drive, AirDrop, or by temporarily serving it from a web server).

## 2. Install per device

Follow the instructions for your specific operating system or device.

### Linux (Debian/Ubuntu-based)

To install system-wide:

```sh
sudo cp atlas-ca.crt /usr/local/share/ca-certificates/atlas-ca.crt
sudo update-ca-certificates
```

For **Firefox**, which uses its own certificate store:
1. Open Firefox.
2. Go to Settings → Privacy & Security.
3. Scroll down to the "Certificates" section and click "View Certificates...".
4. Go to the "Authorities" tab.
5. Click "Import...", select the `atlas-ca.crt` file, and check "Trust this CA to identify websites."

### Linux (Fedora/RHEL-based)

To install system-wide:

```sh
sudo cp atlas-ca.crt /etc/pki/ca-trust/source/anchors/atlas-ca.crt
sudo update-ca-trust
```

### macOS

To install to the System keychain (requires administrator privileges):

```sh
sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain atlas-ca.crt
```

Alternatively, you can double-click the `atlas-ca.crt` file, which will open Keychain Access. Drag the certificate to the "System" keychain, then double-click it and set "When using this certificate" to "Always Trust".

### Windows

1. Press `Win + R`, type `certlm.msc`, and press Enter to open the Certificate Manager for the local machine.
2. In the left pane, navigate to "Trusted Root Certification Authorities" → "Certificates".
3. Right-click on "Certificates", then select "All Tasks" → "Import...".
4. Follow the Certificate Import Wizard:
   - Click "Next".
   - Browse to and select your `atlas-ca.crt` file.
   - Click "Next".
   - Ensure "Place all certificates in the following store" is set to "Trusted Root Certification Authorities".
   - Click "Next", then "Finish".

### Android

1. Transfer the `atlas-ca.crt` file to your Android device.
2. Go to Settings → Security (or "Security & privacy") → Encryption & credentials → Install a certificate → CA certificate.
3. Select the `atlas-ca.crt` file.
4. You may be prompted to set a screen lock if you don't have one.

This installs the certificate to the user store, which is sufficient for Chrome and most applications. Installing to the system store typically requires a rooted device.

### iOS/iPadOS

1. Transfer the `atlas-ca.crt` file to your iOS/iPadOS device (e.g., via AirDrop, email, or by downloading from a web server).
2. Tap the `.crt` file. This will prompt you to install a profile.
3. Go to Settings → General → VPN & Device Management.
4. Under "DOWNLOADED PROFILE", tap on the "atlas-ca" profile and then "Install".
5. After installation, you must explicitly enable full trust:
   - Go to Settings → General → About → Certificate Trust Settings.
   - Under "ENABLE FULL TRUST FOR ROOT CERTIFICATES", toggle on the switch for "atlas-ca".

## 3. Don't forget DNS

Trusting the CA only resolves TLS certificate warnings. Your device still needs to be able to resolve `*.atlas.lan` hostnames to the correct IP addresses.

You have a few options:

- **Add entries to your hosts file:**
  Edit your system's hosts file (e.g., `/etc/hosts` on Linux/macOS, `C:\\Windows\\System32\\drivers\\etc\\hosts` on Windows) and add entries like this, replacing `10.0.0.110` with the actual IP of one of your Traefik ingress nodes:
  ```
  10.0.0.110 git.atlas.lan registry.atlas.lan argocd.atlas.lan redop.atlas.lan
  ```
- **Configure your device to use the Pi-hole DNS server:**
  Once the Pi-hole (`10.0.0.107`) is provisioned and configured for `atlas.lan` resolution (as per ADR 0001), you can configure your device to use it as its primary DNS server.

## 4. Verify

After installing the certificate and configuring DNS, you can verify that TLS trust is established:

```sh
curl --cacert atlas-ca.crt -o /dev/null -w '%{http_code}\n' https://git.atlas.lan/
# Expected output: 200
```

Alternatively, simply open a web browser and navigate to `https://git.atlas.lan/` (or any other `*.atlas.lan` service). The padlock icon should now indicate a secure connection without any certificate warnings.

## Caveats

- This is a **private trust root**: any certificate signed by `atlas-ca` (i.e., all certificates for `*.atlas.lan` services) will be trusted on devices where `atlas-ca` is installed. Only install this CA on devices you control and trust.
- The `atlas-ca` public certificate is also published as ConfigMaps in the `argocd` and `gitea` Kubernetes namespaces (under the `ca.crt` key) if you need to retrieve it from a source other than `kubectl`.
- If the `atlas-ca` ever needs to be replaced, you will need to re-install the new root certificate on all client devices. Refer to `docs/gitops-platform.md` under the "Recovery" section for details on "CA lost" scenarios.