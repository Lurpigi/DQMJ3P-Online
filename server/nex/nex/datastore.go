package nex

import (
	"bytes"
	"database/sql"
	"fmt"
	"io"
	"mime"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"dqmj3p-online/nex/globals"
	"github.com/PretendoNetwork/nex-go/v2"
	"github.com/PretendoNetwork/nex-go/v2/types"
	datastore "github.com/PretendoNetwork/nex-protocols-go/v2/datastore"
	datastore_constants "github.com/PretendoNetwork/nex-protocols-go/v2/datastore/constants"
	datastore_types "github.com/PretendoNetwork/nex-protocols-go/v2/datastore/types"
	"github.com/lib/pq"
)

// * DataStore (115) for the G-Cup (Ranking Race) replays: the game searches the replay of a ranked
// * player (SearchObject by owner), downloads it (PrepareGetObject + HTTP GET), posts its own
// * (PreparePostObject + HTTP POST + CompletePostObject) or replaces it (PrepareUpdateObject +
// * CompleteUpdateObject) and deletes it (DeleteObject).
// * Metadata lives in Postgres (datastore.objects), object data in files served by a small HTTP
// * server in this process instead of S3:
// *   PN_DQMJ3P_DATASTORE_HTTP  listen address (default 127.0.0.1:45080)
// *   PN_DQMJ3P_DATASTORE_URL   base URL given to the clients (default http://<listen address>)
// *   PN_DQMJ3P_DATASTORE_DIR   object directory (default datastore)

var dataStoreDir string
var dataStoreURL string

func initDataStoreTables() {
	_, err := globals.Postgres.Exec(`CREATE SCHEMA IF NOT EXISTS datastore;
		CREATE TABLE IF NOT EXISTS datastore.objects (
			data_id bigserial PRIMARY KEY,
			owner bigint NOT NULL,
			size bigint NOT NULL,
			name text NOT NULL,
			data_type integer NOT NULL,
			meta_binary bytea NOT NULL,
			permission integer NOT NULL,
			del_permission integer NOT NULL,
			flag bigint NOT NULL,
			period integer NOT NULL,
			refer_data_id bigint NOT NULL,
			tags text[] NOT NULL,
			persistence_slot_id integer NOT NULL,
			version integer NOT NULL DEFAULT 0,
			upload_completed boolean NOT NULL DEFAULT false,
			created_time timestamp NOT NULL,
			updated_time timestamp NOT NULL);`)
	if err != nil {
		globals.Logger.Criticalf("Failed to create the datastore tables: %v", err)
	}
}

// * The file part of a multipart upload: the part named "file" or with a file name, else the
// * last part (the form fields come first). Split by hand: the multipart body Azahar sends for
// * the game is not accepted by mime/multipart ("bufio: buffer full").
func multipartFile(contentType string, body []byte) ([]byte, error) {
	_, params, err := mime.ParseMediaType(contentType)
	if err != nil {
		return nil, err
	}
	delimiter := []byte("--" + params["boundary"])
	// * Azahar sends the first 32 KiB chunk of a chunked upload last: the body starts with the
	// * middle of the file and the opening delimiter comes later. Rotate it back into order.
	if open := bytes.Index(body, append(delimiter, '\r', '\n')); open > 0 &&
		len(bytes.TrimSpace(body[:open])) > 0 {
		body = append(append([]byte{}, body[open:]...), body[:open]...)
	}
	var last []byte
	for _, part := range bytes.Split(body, delimiter) {
		// * Each part: CRLF, headers, blank line, data, CRLF. The closing delimiter leaves "--".
		head, data, found := bytes.Cut(part, []byte("\r\n\r\n"))
		if !found {
			continue
		}
		data = bytes.TrimSuffix(data, []byte("\r\n"))
		headers := strings.ToLower(string(head))
		if strings.Contains(headers, "filename=") || strings.Contains(headers, `name="file"`) {
			return data, nil
		}
		last = data
	}
	if last == nil {
		return nil, fmt.Errorf("no parts in multipart body")
	}
	return last, nil
}

func dataStoreFile(dataID uint64) string {
	return filepath.Join(dataStoreDir, fmt.Sprintf("%d.bin", dataID))
}

func dataStoreUploadFile(dataID uint64, version uint32) string {
	return filepath.Join(dataStoreDir, fmt.Sprintf("%d.v%d.upload", dataID, version))
}

// * POST /upload/<dataID>/<version> (multipart with a file part, or a raw body), GET /data/<dataID>
func serveDataStoreHTTP(listen string) {
	mux := http.NewServeMux()
	mux.HandleFunc("/upload/", func(w http.ResponseWriter, r *http.Request) {
		parts := strings.Split(strings.TrimPrefix(r.URL.Path, "/upload/"), "/")
		if len(parts) != 2 || (r.Method != http.MethodPost && r.Method != http.MethodPut) {
			http.Error(w, "bad request", http.StatusBadRequest)
			return
		}
		dataID, err1 := strconv.ParseUint(parts[0], 10, 64)
		version, err2 := strconv.ParseUint(parts[1], 10, 32)
		if err1 != nil || err2 != nil {
			http.Error(w, "bad request", http.StatusBadRequest)
			return
		}

		data, err := io.ReadAll(io.LimitReader(r.Body, 16<<20))
		if err == nil && os.Getenv("PN_DQMJ3P_DEBUG_RMC") == "1" {
			// * Raw request kept for reverse engineering the replay format (one file per attempt:
			// * the client retries with an empty body).
			raw := fmt.Sprintf("%s.%d.raw", dataStoreUploadFile(dataID, uint32(version)), time.Now().UnixNano())
			_ = os.WriteFile(raw, data, 0o644)
		}
		if err == nil && strings.HasPrefix(r.Header.Get("Content-Type"), "multipart/form-data") {
			data, err = multipartFile(r.Header.Get("Content-Type"), data)
		}
		if err == nil {
			err = os.WriteFile(dataStoreUploadFile(dataID, uint32(version)), data, 0o644)
		}
		if err != nil {
			globals.Logger.Errorf("DataStore upload %d: %v", dataID, err)
			http.Error(w, "write failed", http.StatusInternalServerError)
			return
		}
		globals.Logger.Infof("DataStore: received %d bytes for object %d (version %d)", len(data), dataID, version)
		w.WriteHeader(http.StatusOK)
	})
	mux.HandleFunc("/data/", func(w http.ResponseWriter, r *http.Request) {
		dataID, err := strconv.ParseUint(strings.TrimPrefix(r.URL.Path, "/data/"), 10, 64)
		if err != nil {
			http.NotFound(w, r)
			return
		}
		http.ServeFile(w, r, dataStoreFile(dataID))
	})
	logged := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		globals.Logger.Infof("DataStore HTTP: %s %s (Content-Type %q, %d bytes)", r.Method, r.URL.Path,
			r.Header.Get("Content-Type"), r.ContentLength)
		mux.ServeHTTP(w, r)
	})
	if err := http.ListenAndServe(listen, logged); err != nil {
		globals.Logger.Criticalf("DataStore HTTP server: %v", err)
	}
}

type dataStoreObject struct {
	dataID, owner, size, flag, referDataID uint64
	name                                   string
	dataType, permission, delPermission    uint16
	period, version                        uint32
	metaBinary                             []byte
	tags                                   []string
	created, updated                       time.Time
}

const dataStoreObjectColumns = `data_id, owner, size, name, data_type, meta_binary, permission, del_permission,
	flag, period, refer_data_id, tags, version, created_time, updated_time`

func scanDataStoreObject(row interface{ Scan(...any) error }) (dataStoreObject, error) {
	var o dataStoreObject
	err := row.Scan(&o.dataID, &o.owner, &o.size, &o.name, &o.dataType, &o.metaBinary, &o.permission,
		&o.delPermission, &o.flag, &o.period, &o.referDataID, pq.Array(&o.tags), &o.version, &o.created, &o.updated)
	return o, err
}

func getDataStoreObject(dataID uint64) (dataStoreObject, *nex.Error) {
	o, err := scanDataStoreObject(globals.Postgres.QueryRow(`SELECT `+dataStoreObjectColumns+`
		FROM datastore.objects WHERE data_id = $1 AND upload_completed`, dataID))
	if err == sql.ErrNoRows {
		return o, nex.NewError(nex.ResultCodes.DataStore.NotFound, "change_error")
	} else if err != nil {
		globals.Logger.Error(err.Error())
		return o, nex.NewError(nex.ResultCodes.DataStore.Unknown, "change_error")
	}
	return o, nil
}

func (o dataStoreObject) metaInfo() datastore_types.DataStoreMetaInfo {
	info := datastore_types.NewDataStoreMetaInfo()
	info.DataID = types.NewUInt64(o.dataID)
	info.OwnerID = types.NewPID(o.owner)
	info.Size = types.NewUInt32(uint32(o.size))
	info.Name = types.NewString(o.name)
	info.DataType = types.NewUInt16(o.dataType)
	info.MetaBinary = types.NewQBuffer(o.metaBinary)
	info.Permission.Permission = datastore_constants.Permission(o.permission)
	info.DelPermission.Permission = datastore_constants.Permission(o.delPermission)
	created, updated := types.NewDateTime(0), types.NewDateTime(0)
	info.CreatedTime = created.FromTimestamp(o.created)
	info.UpdatedTime = updated.FromTimestamp(o.updated)
	info.Period = types.NewUInt16(uint16(o.period))
	info.ReferDataID = types.NewUInt32(uint32(o.referDataID))
	info.Flag = datastore_constants.DataFlag(o.flag)
	referred, expire := types.NewDateTime(0), types.NewDateTime(0)
	info.ReferredTime = referred.FromTimestamp(o.created)
	info.ExpireTime = expire.FromTimestamp(o.updated.AddDate(0, 0, int(o.period)))
	for _, tag := range o.tags {
		info.Tags = append(info.Tags, types.NewString(tag))
	}
	return info
}

func dataStoreResponse(packet nex.PacketInterface, callID uint32, methodID uint32, body types.RVType) *nex.RMCMessage {
	endpoint := packet.Sender().Endpoint()
	var bytes []byte
	if body != nil {
		stream := nex.NewByteStreamOut(endpoint.LibraryVersions(), endpoint.ByteStreamSettings())
		body.WriteTo(stream)
		bytes = stream.Bytes()
	}
	response := nex.NewRMCSuccess(endpoint, bytes)
	response.ProtocolID = datastore.ProtocolID
	response.MethodID = methodID
	response.CallID = callID
	return response
}

func uploadURL(dataID uint64, version uint32) string {
	return fmt.Sprintf("%s/upload/%d/%d", dataStoreURL, dataID, version)
}

func searchObject(err error, packet nex.PacketInterface, callID uint32, param datastore_types.DataStoreSearchParam) (*nex.RMCMessage, *nex.Error) {
	if err != nil {
		globals.Logger.Error(err.Error())
		return nil, nex.NewError(nex.ResultCodes.DataStore.InvalidArgument, "change_error")
	}

	query := `SELECT ` + dataStoreObjectColumns + ` FROM datastore.objects WHERE upload_completed`
	var args []any
	if len(param.OwnerIDs) > 0 {
		owners := make([]int64, 0, len(param.OwnerIDs))
		for _, pid := range param.OwnerIDs {
			owners = append(owners, int64(pid))
		}
		args = append(args, pq.Array(owners))
		query += fmt.Sprintf(" AND owner = ANY($%d)", len(args))
	}
	if uint16(param.DataType) != 0xFFFF {
		args = append(args, uint16(param.DataType))
		query += fmt.Sprintf(" AND data_type = $%d", len(args))
	}
	if len(param.Tags) > 0 {
		tags := make([]string, 0, len(param.Tags))
		for _, tag := range param.Tags {
			tags = append(tags, string(tag))
		}
		args = append(args, pq.Array(tags))
		query += fmt.Sprintf(" AND tags @> $%d", len(args))
	}
	query += " ORDER BY updated_time DESC"

	rows, dbErr := globals.Postgres.Query(query, args...)
	if dbErr != nil {
		globals.Logger.Error(dbErr.Error())
		return nil, nex.NewError(nex.ResultCodes.DataStore.Unknown, "change_error")
	}
	defer rows.Close()

	result := datastore_types.NewDataStoreSearchResult()
	total := uint32(0)
	for rows.Next() {
		o, err := scanDataStoreObject(rows)
		if err != nil {
			globals.Logger.Error(err.Error())
			return nil, nex.NewError(nex.ResultCodes.DataStore.Unknown, "change_error")
		}
		total++
		if total <= uint32(param.ResultRange.Offset) ||
			uint32(len(result.Result)) >= uint32(param.ResultRange.Length) {
			continue
		}
		info := o.metaInfo()
		info.FilterPropertiesByResultOption(param.ResultOption)
		result.Result = append(result.Result, info)
	}
	result.TotalCount = types.NewUInt32(total)
	return dataStoreResponse(packet, callID, datastore.MethodSearchObject, result), nil
}

func preparePostObject(err error, packet nex.PacketInterface, callID uint32, param datastore_types.DataStorePreparePostParam) (*nex.RMCMessage, *nex.Error) {
	if err != nil {
		globals.Logger.Error(err.Error())
		return nil, nex.NewError(nex.ResultCodes.DataStore.InvalidArgument, "change_error")
	}
	owner := uint64(packet.Sender().PID())
	slot := uint16(param.PersistenceInitParam.PersistenceSlotID)

	tags := make([]string, 0, len(param.Tags))
	for _, tag := range param.Tags {
		tags = append(tags, string(tag))
	}
	now := time.Now().UTC()
	var dataID uint64
	dbErr := globals.Postgres.QueryRow(`INSERT INTO datastore.objects
		(owner, size, name, data_type, meta_binary, permission, del_permission, flag, period,
		 refer_data_id, tags, persistence_slot_id, created_time, updated_time)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $13) RETURNING data_id`,
		owner, uint32(param.Size), string(param.Name), uint16(param.DataType), []byte(param.MetaBinary),
		uint8(param.Permission.Permission), uint8(param.DelPermission.Permission), uint32(param.Flag),
		uint16(param.Period), uint32(param.ReferDataID), pq.Array(tags), int(slot), now).Scan(&dataID)
	if dbErr != nil {
		globals.Logger.Error(dbErr.Error())
		return nil, nex.NewError(nex.ResultCodes.DataStore.Unknown, "change_error")
	}

	info := datastore_types.NewDataStoreReqPostInfo()
	info.DataID = types.NewUInt64(dataID)
	info.URL = types.NewString(uploadURL(dataID, 0))
	return dataStoreResponse(packet, callID, datastore.MethodPreparePostObject, info), nil
}

func completePostObject(err error, packet nex.PacketInterface, callID uint32, param datastore_types.DataStoreCompletePostParam) (*nex.RMCMessage, *nex.Error) {
	if err != nil {
		globals.Logger.Error(err.Error())
		return nil, nex.NewError(nex.ResultCodes.DataStore.InvalidArgument, "change_error")
	}
	dataID := uint64(param.DataID)
	owner := uint64(packet.Sender().PID())

	var size uint64
	var slot int
	dbErr := globals.Postgres.QueryRow(`SELECT size, persistence_slot_id FROM datastore.objects
		WHERE data_id = $1 AND owner = $2 AND NOT upload_completed`, dataID, owner).Scan(&size, &slot)
	if dbErr == sql.ErrNoRows {
		return nil, nex.NewError(nex.ResultCodes.DataStore.PermissionDenied, "change_error")
	} else if dbErr != nil {
		globals.Logger.Error(dbErr.Error())
		return nil, nex.NewError(nex.ResultCodes.DataStore.Unknown, "change_error")
	}

	upload := dataStoreUploadFile(dataID, 0)
	if !bool(param.IsSuccess) {
		os.Remove(upload)
		globals.Postgres.Exec(`DELETE FROM datastore.objects WHERE data_id = $1`, dataID)
		return dataStoreResponse(packet, callID, datastore.MethodCompletePostObject, nil), nil
	}
	stat, statErr := os.Stat(upload)
	if statErr != nil || uint64(stat.Size()) != size {
		globals.Logger.Errorf("DataStore: object %d upload missing or wrong size", dataID)
		return nil, nex.NewError(nex.ResultCodes.DataStore.NotFound, "change_error")
	}
	if err := os.Rename(upload, dataStoreFile(dataID)); err != nil {
		globals.Logger.Error(err.Error())
		return nil, nex.NewError(nex.ResultCodes.DataStore.Unknown, "change_error")
	}

	// * One object per owner and persistence slot: the new one replaces the old one
	if slot != 0xFFFF {
		var old []int64
		rows, _ := globals.Postgres.Query(`DELETE FROM datastore.objects WHERE owner = $1
			AND persistence_slot_id = $2 AND data_id <> $3 RETURNING data_id`, owner, slot, dataID)
		if rows != nil {
			for rows.Next() {
				var id int64
				rows.Scan(&id)
				old = append(old, id)
			}
			rows.Close()
		}
		for _, id := range old {
			os.Remove(dataStoreFile(uint64(id)))
		}
	}
	globals.Postgres.Exec(`UPDATE datastore.objects SET upload_completed = true WHERE data_id = $1`, dataID)
	return dataStoreResponse(packet, callID, datastore.MethodCompletePostObject, nil), nil
}

func prepareGetObject(err error, packet nex.PacketInterface, callID uint32, param datastore_types.DataStorePrepareGetParam) (*nex.RMCMessage, *nex.Error) {
	if err != nil {
		globals.Logger.Error(err.Error())
		return nil, nex.NewError(nex.ResultCodes.DataStore.InvalidArgument, "change_error")
	}
	dataID := uint64(param.DataID)
	if dataID == 0 {
		dbErr := globals.Postgres.QueryRow(`SELECT data_id FROM datastore.objects WHERE owner = $1
			AND persistence_slot_id = $2 AND upload_completed ORDER BY data_id DESC LIMIT 1`,
			uint64(param.PersistenceTarget.OwnerID), uint16(param.PersistenceTarget.PersistenceSlotID)).Scan(&dataID)
		if dbErr != nil {
			return nil, nex.NewError(nex.ResultCodes.DataStore.NotFound, "change_error")
		}
	}
	o, errCode := getDataStoreObject(dataID)
	if errCode != nil {
		return nil, errCode
	}

	info := datastore_types.NewDataStoreReqGetInfo()
	info.URL = types.NewString(fmt.Sprintf("%s/data/%d", dataStoreURL, dataID))
	info.Size = types.NewUInt32(uint32(o.size))
	info.DataID = types.NewUInt64(dataID)
	return dataStoreResponse(packet, callID, datastore.MethodPrepareGetObject, info), nil
}

func prepareUpdateObject(err error, packet nex.PacketInterface, callID uint32, param datastore_types.DataStorePrepareUpdateParam) (*nex.RMCMessage, *nex.Error) {
	if err != nil {
		globals.Logger.Error(err.Error())
		return nil, nex.NewError(nex.ResultCodes.DataStore.InvalidArgument, "change_error")
	}
	o, errCode := getDataStoreObject(uint64(param.DataID))
	if errCode != nil {
		return nil, errCode
	}
	if o.owner != uint64(packet.Sender().PID()) {
		return nil, nex.NewError(nex.ResultCodes.DataStore.PermissionDenied, "change_error")
	}

	info := datastore_types.NewDataStoreReqUpdateInfo()
	info.Version = types.NewUInt32(o.version + 1)
	info.URL = types.NewString(uploadURL(o.dataID, o.version+1))
	return dataStoreResponse(packet, callID, datastore.MethodPrepareUpdateObject, info), nil
}

func completeUpdateObject(err error, packet nex.PacketInterface, callID uint32, param datastore_types.DataStoreCompleteUpdateParam) (*nex.RMCMessage, *nex.Error) {
	if err != nil {
		globals.Logger.Error(err.Error())
		return nil, nex.NewError(nex.ResultCodes.DataStore.InvalidArgument, "change_error")
	}
	o, errCode := getDataStoreObject(uint64(param.DataID))
	if errCode != nil {
		return nil, errCode
	}
	if o.owner != uint64(packet.Sender().PID()) {
		return nil, nex.NewError(nex.ResultCodes.DataStore.PermissionDenied, "change_error")
	}

	upload := dataStoreUploadFile(o.dataID, uint32(param.Version))
	if bool(param.IsSuccess) {
		stat, statErr := os.Stat(upload)
		if statErr != nil {
			return nil, nex.NewError(nex.ResultCodes.DataStore.NotFound, "change_error")
		}
		if err := os.Rename(upload, dataStoreFile(o.dataID)); err != nil {
			globals.Logger.Error(err.Error())
			return nil, nex.NewError(nex.ResultCodes.DataStore.Unknown, "change_error")
		}
		globals.Postgres.Exec(`UPDATE datastore.objects SET size = $2, version = $3, updated_time = $4
			WHERE data_id = $1`, o.dataID, stat.Size(), uint32(param.Version), time.Now().UTC())
	} else {
		os.Remove(upload)
	}
	return dataStoreResponse(packet, callID, datastore.MethodCompleteUpdateObject, nil), nil
}

func deleteObject(err error, packet nex.PacketInterface, callID uint32, param datastore_types.DataStoreDeleteParam) (*nex.RMCMessage, *nex.Error) {
	if err != nil {
		globals.Logger.Error(err.Error())
		return nil, nex.NewError(nex.ResultCodes.DataStore.InvalidArgument, "change_error")
	}
	result, dbErr := globals.Postgres.Exec(`DELETE FROM datastore.objects WHERE data_id = $1 AND owner = $2`,
		uint64(param.DataID), uint64(packet.Sender().PID()))
	if dbErr != nil {
		globals.Logger.Error(dbErr.Error())
		return nil, nex.NewError(nex.ResultCodes.DataStore.Unknown, "change_error")
	}
	if n, _ := result.RowsAffected(); n == 0 {
		return nil, nex.NewError(nex.ResultCodes.DataStore.NotFound, "change_error")
	}
	os.Remove(dataStoreFile(uint64(param.DataID)))
	return dataStoreResponse(packet, callID, datastore.MethodDeleteObject, nil), nil
}

func registerDataStoreProtocol() {
	initDataStoreTables()

	listen := os.Getenv("PN_DQMJ3P_DATASTORE_HTTP")
	if listen == "" {
		listen = "127.0.0.1:45080"
	}
	dataStoreURL = strings.TrimRight(os.Getenv("PN_DQMJ3P_DATASTORE_URL"), "/")
	if dataStoreURL == "" {
		dataStoreURL = "http://" + listen
	}
	dataStoreDir = os.Getenv("PN_DQMJ3P_DATASTORE_DIR")
	if dataStoreDir == "" {
		dataStoreDir = "datastore"
	}
	if err := os.MkdirAll(dataStoreDir, 0o755); err != nil {
		globals.Logger.Criticalf("DataStore directory: %v", err)
	}
	go serveDataStoreHTTP(listen)

	dataStoreProtocol := datastore.NewProtocol()
	globals.SecureEndpoint.RegisterServiceProtocol(dataStoreProtocol)
	dataStoreProtocol.SetHandlerSearchObject(searchObject)
	dataStoreProtocol.SetHandlerPreparePostObject(preparePostObject)
	dataStoreProtocol.SetHandlerCompletePostObject(completePostObject)
	dataStoreProtocol.SetHandlerPrepareGetObject(prepareGetObject)
	dataStoreProtocol.SetHandlerPrepareUpdateObject(prepareUpdateObject)
	dataStoreProtocol.SetHandlerCompleteUpdateObject(completeUpdateObject)
	dataStoreProtocol.SetHandlerDeleteObject(deleteObject)
}
