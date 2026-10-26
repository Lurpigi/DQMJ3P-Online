package main

import (
	"database/sql"
	"fmt"
	"os"
	"strconv"
	"strings"

	"dqmj3p-online/nex/globals"
	pbfriends "github.com/PretendoNetwork/grpc/go/friends"
	common_globals "github.com/PretendoNetwork/nex-protocols-common-go/v2/globals"
	"github.com/PretendoNetwork/plogger-go"
	"github.com/joho/godotenv"
	_ "github.com/lib/pq"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/metadata"
)

func requireEnv(name string) string {
	value := strings.TrimSpace(os.Getenv(name))
	if value == "" {
		globals.Logger.Errorf("%s environment variable not set", name)
		os.Exit(0)
	}

	return value
}

func requirePortEnv(name string) uint16 {
	value := requireEnv(name)
	port, err := strconv.Atoi(value)
	if err != nil || port < 0 || port > 65535 {
		globals.Logger.Errorf("%s is not a valid port. Expected 0-65535, got %s", name, value)
		os.Exit(0)
	}

	return uint16(port)
}

func init() {
	globals.Logger = plogger.NewLogger()

	var err error

	err = godotenv.Load()
	if err != nil {
		globals.Logger.Warning("Error loading .env file")
	}

	kerberosPassword := os.Getenv("PN_DQMJ3P_KERBEROS_PASSWORD")
	if strings.TrimSpace(kerberosPassword) == "" {
		globals.Logger.Warningf("PN_DQMJ3P_KERBEROS_PASSWORD environment variable not set. Using default password: %q", globals.KerberosPassword)
	} else {
		globals.KerberosPassword = kerberosPassword
	}

	globals.InitAccounts()

	requirePortEnv("PN_DQMJ3P_AUTHENTICATION_SERVER_PORT")
	requireEnv("PN_DQMJ3P_SECURE_SERVER_HOST")
	requirePortEnv("PN_DQMJ3P_SECURE_SERVER_PORT")

	// * Dev mode: every PID logs in with the same NEX password and nobody has friends.
	// * Lets the server run without the Pretendo account/friends services, for local tests only.
	globals.DevPassword = os.Getenv("PN_DQMJ3P_DEV_PASSWORD")
	if globals.DevPassword != "" {
		globals.Logger.Warning("PN_DQMJ3P_DEV_PASSWORD is set: running in DEV mode without account/friends gRPC. Never use this in production")
	} else {
		accountGRPCHost := requireEnv("PN_DQMJ3P_ACCOUNT_GRPC_HOST")
		accountGRPCPort := requirePortEnv("PN_DQMJ3P_ACCOUNT_GRPC_PORT")
		accountGRPCAPIKey := os.Getenv("PN_DQMJ3P_ACCOUNT_GRPC_API_KEY")
		if strings.TrimSpace(accountGRPCAPIKey) == "" {
			globals.Logger.Warning("Insecure gRPC server detected. PN_DQMJ3P_ACCOUNT_GRPC_API_KEY environment variable not set")
		}

		common_globals.ConnectToAccountGRPC(accountGRPCHost, accountGRPCPort, accountGRPCAPIKey)

		friendsGRPCHost := requireEnv("PN_DQMJ3P_FRIENDS_GRPC_HOST")
		friendsGRPCPort := requirePortEnv("PN_DQMJ3P_FRIENDS_GRPC_PORT")
		friendsGRPCAPIKey := os.Getenv("PN_DQMJ3P_FRIENDS_GRPC_API_KEY")
		if strings.TrimSpace(friendsGRPCAPIKey) == "" {
			globals.Logger.Warning("Insecure gRPC server detected. PN_DQMJ3P_FRIENDS_GRPC_API_KEY environment variable not set")
		}

		globals.GRPCFriendsClientConnection, err = grpc.Dial(fmt.Sprintf("%s:%d", friendsGRPCHost, friendsGRPCPort), grpc.WithTransportCredentials(insecure.NewCredentials()))
		if err != nil {
			globals.Logger.Criticalf("Failed to connect to friends gRPC server: %v", err)
			os.Exit(0)
		}

		globals.GRPCFriendsClient = pbfriends.NewFriendsClient(globals.GRPCFriendsClientConnection)
		globals.GRPCFriendsCommonMetadata = metadata.Pairs(
			"X-API-Key", friendsGRPCAPIKey,
		)
	}

	globals.Postgres, err = sql.Open("postgres", requireEnv("PN_DQMJ3P_POSTGRES_URI"))
	if err != nil {
		globals.Logger.Critical(err.Error())
		os.Exit(0)
	}

	if err = globals.Postgres.Ping(); err != nil {
		globals.Logger.Criticalf("Failed to connect to Postgres: %v", err)
		os.Exit(0)
	}
}
