package globals

import (
	"crypto/subtle"
	"database/sql"
	"errors"
	"regexp"
	"sync"

	"github.com/PretendoNetwork/nex-go/v2"
	"github.com/PretendoNetwork/nex-go/v2/types"
	ticket_granting_types "github.com/PretendoNetwork/nex-protocols-go/v2/ticket-granting/types"
)

// * The patch sends the player password as the LoginEx token: the first 8 bytes of
// * MD5(salt + friends password) in hex (make_url_patch.py --nex-player-password). The first login
// * of a PID stores it, later logins must match. The ticket is encrypted with this password, so a
// * client that only knows the PID can't use it.
var playerPasswordRegex = regexp.MustCompile(`^[0-9a-f]{16}$`)

// * Accounts of PIDs without a password, between AccountDetailsByUsername and ValidatePlayerLogin
var unregisteredAccounts sync.Map

// InitPasswordTable creates the player password table
func InitPasswordTable() {
	_, err := Postgres.Exec(`CREATE SCHEMA IF NOT EXISTS accounts;
		CREATE TABLE IF NOT EXISTS accounts.passwords (
			pid bigint PRIMARY KEY,
			password text NOT NULL,
			created timestamp NOT NULL DEFAULT now()
		)`)
	if err != nil {
		Logger.Critical(err.Error())
		panic(err)
	}
}

func storedPassword(pid types.PID) (string, error) {
	var password string
	err := Postgres.QueryRow(`SELECT password FROM accounts.passwords WHERE pid = $1`, uint32(pid)).Scan(&password)
	return password, err
}

// PasswordFromPID returns the NEX password of a registered player
func PasswordFromPID(pid *types.PID) (string, uint32) {
	if DevPassword != "" {
		return DevPassword, 0
	}

	password, err := storedPassword(*pid)
	if errors.Is(err, sql.ErrNoRows) {
		return "", nex.ResultCodes.RendezVous.InvalidUsername
	}

	if err != nil {
		Logger.Error(err.Error())
		return "", nex.ResultCodes.Core.Exception
	}

	return password, 0
}

// ValidatePlayerLogin checks the LoginEx token against the stored password, or stores it on the first login
func ValidatePlayerLogin(pid types.PID, loginData types.DataHolder) *nex.Error {
	unregistered, _ := unregisteredAccounts.LoadAndDelete(pid)

	authenticationInfo, ok := loginData.Object.Copy().(ticket_granting_types.AuthenticationInfo)
	if !ok {
		return nex.NewError(nex.ResultCodes.Authentication.ValidationFailed, "Unexpected login data")
	}

	token := string(authenticationInfo.Token)
	if !playerPasswordRegex.MatchString(token) {
		return nex.NewError(nex.ResultCodes.Authentication.ValidationFailed, "Invalid player password")
	}

	if unregistered != nil {
		_, err := Postgres.Exec(`INSERT INTO accounts.passwords (pid, password) VALUES ($1, $2) ON CONFLICT (pid) DO NOTHING`, uint32(pid), token)
		if err != nil {
			Logger.Error(err.Error())
			return nex.NewError(nex.ResultCodes.Core.Exception, "Failed to store player password")
		}
	}

	password, err := storedPassword(pid)
	if err != nil {
		Logger.Error(err.Error())
		return nex.NewError(nex.ResultCodes.Core.Exception, "Failed to read player password")
	}

	if subtle.ConstantTimeCompare([]byte(password), []byte(token)) != 1 {
		return nex.NewError(nex.ResultCodes.RendezVous.InvalidPassword, "Wrong player password")
	}

	if unregistered != nil {
		unregistered.(*nex.Account).Password = password
	}

	return nil
}
