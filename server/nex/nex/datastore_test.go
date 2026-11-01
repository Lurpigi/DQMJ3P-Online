package nex

import (
	"bytes"
	"crypto/rand"
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
