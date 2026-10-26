package nex

import (
	"os"

	"dqmj3p-online/nex/globals"
	"github.com/PretendoNetwork/nex-go/v2"
)

// logRMC prints every RMC request. With PN_DQMJ3P_DEBUG_RMC=1 it also dumps the raw
// parameters, which is how we discover the methods/arguments the game really sends.
func logRMC(server string, packet nex.PacketInterface) {
	request := packet.RMCMessage()
	globals.Logger.Infof("[%s] PID %v -> protocol %d method %d (call %d)", server, packet.Sender().PID(), request.ProtocolID, request.MethodID, request.CallID)

	if os.Getenv("PN_DQMJ3P_DEBUG_RMC") == "1" {
		globals.Logger.Infof("[%s] params: %x", server, request.Parameters)
	}
}
