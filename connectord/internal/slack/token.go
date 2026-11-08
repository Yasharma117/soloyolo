package slack

import (
	"errors"
	"os"
	"os/exec"
	"runtime"
	"strings"
)

// Tokens never touch the repo or the shared store. They come from the environment
// (SLACK_USER_TOKEN, SLACK_APP_TOKEN) or the OS keychain, under these service names with the
// connectord account id (e.g. "slack-1") as the account.
const (
	keychainService    = "soloyolo-slack"     // the xoxp- user token
	keychainAppService = "soloyolo-slack-app" // the optional xapp- app-level token, for Socket Mode
)

// Keychain stores secrets outside the data directory.
type Keychain interface {
	Get(service, account string) (string, error)
	Set(service, account, secret string) error
}

var errNoKeychain = errors.New("no OS keychain on this platform")

// osKeychain shells out to the platform tool, so there is no cgo and no extra dependency:
// macOS `security` (login keychain) and Linux `secret-tool` (libsecret: GNOME Keyring, KWallet).
type osKeychain struct{}

func (osKeychain) Get(service, account string) (string, error) {
	var cmd *exec.Cmd
	switch runtime.GOOS {
	case "darwin":
		cmd = exec.Command("security", "find-generic-password", "-s", service, "-a", account, "-w")
	case "linux":
		cmd = exec.Command("secret-tool", "lookup", "service", service, "account", account)
	default:
		return "", errNoKeychain
	}
	out, err := cmd.Output()
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(string(out)), nil
}

func (osKeychain) Set(service, account, secret string) error {
	var cmd *exec.Cmd
	switch runtime.GOOS {
	case "darwin":
		// `security` only takes the secret on argv (or an interactive prompt). It is visible to
		// `ps` for the few milliseconds the command runs; acceptable on a single-user Mac.
		cmd = exec.Command("security", "add-generic-password", "-U", "-s", service, "-a", account, "-w", secret)
	case "linux":
		cmd = exec.Command("secret-tool", "store", "--label=soloyolo Slack", "service", service, "account", account)
		cmd.Stdin = strings.NewReader(secret) // stdin, never argv
	default:
		return errNoKeychain
	}
	return cmd.Run()
}

// token returns the first of: the environment variable, the keychain entry.
func (a *Adapter) token(env, service string) string {
	if v := strings.TrimSpace(os.Getenv(env)); v != "" {
		return v
	}
	if a.Keychain == nil {
		return ""
	}
	v, err := a.Keychain.Get(service, a.accountID)
	if err != nil {
		return ""
	}
	return v
}
