package nex

import (
	"os"
	"strconv"

	"dqmj3p-online/nex/globals"
	"github.com/PretendoNetwork/nex-go/v2"
	"github.com/PretendoNetwork/nex-go/v2/constants"
	"github.com/PretendoNetwork/nex-go/v2/types"
	commonticketgranting "github.com/PretendoNetwork/nex-protocols-common-go/v2/ticket-granting"
	ticketgranting "github.com/PretendoNetwork/nex-protocols-go/v2/ticket-granting"
)

func registerCommonAuthenticationServerProtocols() {
	ticketGrantingProtocol := ticketgranting.NewProtocol()
	globals.AuthenticationEndpoint.RegisterServiceProtocol(ticketGrantingProtocol)
	commonTicketGrantingProtocol := commonticketgranting.NewCommonProtocol(ticketGrantingProtocol)
	commonTicketGrantingProtocol.ValidateLoginData = globals.ValidatePlayerLogin

	// * Test clients without a token (NintendoClients) need the plain Login method,
	// * so allow it in DEV mode only
	if globals.DevPassword != "" {
		commonTicketGrantingProtocol.EnableInsecureLogin()

		// * A game patched to skip NASC (make_url_patch.py --nex-auth) sends a dummy token
		// * and logs in with the DEV password, so accept any LoginEx token too
		commonTicketGrantingProtocol.ValidateLoginData = func(pid types.PID, loginData types.DataHolder) *nex.Error {
			return nil
		}
	}

	port, _ := strconv.Atoi(os.Getenv("PN_DQMJ3P_SECURE_SERVER_PORT"))

	secureStationURL := types.NewStationURL("")
	secureStationURL.SetURLType(constants.StationURLPRUDPS)
	secureStationURL.SetAddress(os.Getenv("PN_DQMJ3P_SECURE_SERVER_HOST"))
	secureStationURL.SetPortNumber(uint16(port))
	secureStationURL.SetConnectionID(1)
	secureStationURL.SetPrincipalID(types.NewPID(2))
	secureStationURL.SetStreamID(1)
	secureStationURL.SetStreamType(constants.StreamTypeRVSecure)
	secureStationURL.SetType(uint8(constants.StationURLFlagPublic))

	commonTicketGrantingProtocol.SecureStationURL = secureStationURL
	commonTicketGrantingProtocol.BuildName = types.NewString(globals.ServerBuildString)
	commonTicketGrantingProtocol.SecureServerAccount = globals.SecureServerAccount
}
