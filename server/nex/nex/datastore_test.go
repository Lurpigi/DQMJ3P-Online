package nex

import (
	"bytes"
	"crypto/rand"
	"encoding/binary"
	"slices"
	"sort"
	"testing"
)

func TestMultipartFilePieceOrders(t *testing.T) {
	const boundary = "--------BOUNDARY--------FE56AD3AF077C6E5"
	contentType := "multipart/form-data; boundary=" + boundary

	data := make([]byte, 143056)
	if _, err := rand.Read(data); err != nil {
		t.Fatal(err)
	}
	head := []byte("--" + boundary + "\r\nContent-Disposition: form-data; name=\"key\"\r\n\r\nvalue\r\n" +
		"--" + boundary + "\r\nContent-Disposition: form-data; name=\"file\"\r\n\r\n")
	foot := []byte("\r\n--" + boundary + "--\r\n")

	bodies := map[string][][]byte{
		"in order":               {head, data, foot},
		"sorted":                 {foot, head, data},
		"foot first":             {foot, data, head},
		"data first":             {data, head, foot},
		"head and data together": {foot, append(append([]byte{}, head...), data...)},
	}
	sorted := [][]byte{head, data, foot}
	sort.Slice(sorted, func(i, j int) bool { return bytes.Compare(sorted[i], sorted[j]) < 0 })
	bodies["sorted by content"] = sorted

	for name, pieces := range bodies {
		got, err := multipartFile(contentType, bytes.Join(pieces, nil))
		if err != nil {
			t.Errorf("%s: %v", name, err)
		} else if !bytes.Equal(got, data) {
			t.Errorf("%s: got %d bytes, want the %d bytes of the file", name, len(got), len(data))
		}
	}

	if _, err := multipartFile(contentType, []byte("no delimiters")); err == nil {
		t.Error("body without delimiters accepted")
	}
}

func testReplay(frames int) []byte {
	records := make([]byte, 0, frames*replayRecordSize)
	for frame := 0; frame < frames; frame++ {
		record := make([]byte, replayRecordSize)
		binary.LittleEndian.PutUint32(record, uint32(frame))
		record[4], record[12] = byte(frame), byte(frame%3) // * position, input
		record[19] = 3
		records = append(records, record...)
	}
	tables := make([]byte, 6000)
	for i := range tables {
		tables[i] = byte(i)
	}
	offsets := []uint32{0x18, 0x18 + uint32(len(records))}
	offsets = append(offsets, offsets[1]+2000, offsets[1]+4000, offsets[1]+uint32(len(tables)))
	out := make([]byte, 0x18)
	for i, offset := range offsets {
		binary.LittleEndian.PutUint32(out[i*4:], offset)
	}
	out = append(append(out, records...), tables...)
	return append(out, make([]byte, 116)...) // * team data
}

func TestRepairReplayOrder(t *testing.T) {
	for _, frames := range []int{100, 4195, 6553, 9000, 20000} {
		replay := testReplay(frames)
		if got := repairReplayOrder(replay); !bytes.Equal(got, replay) {
			t.Fatalf("%d frames: a replay in order was changed", frames)
		}
		var pieces [][]byte
		for start := 0; start < len(replay); start += replayPiece {
			pieces = append(pieces, replay[start:min(start+replayPiece, len(replay))])
		}
		slices.SortFunc(pieces, bytes.Compare) // * as Azahar sends them
		if got := repairReplayOrder(bytes.Join(pieces, nil)); !bytes.Equal(got, replay) {
			t.Errorf("%d frames in %d pieces not put back in order", frames, len(pieces))
		}
	}
	// * Not a replay: left as it came
	other := make([]byte, 3*replayPiece)
	if _, err := rand.Read(other); err != nil {
		t.Fatal(err)
	}
	if got := repairReplayOrder(other); !bytes.Equal(got, other) {
		t.Error("random data was changed")
	}
}
