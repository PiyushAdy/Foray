// Package worker reconciles ledger totals against the API on a schedule.
package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"time"
)

type totals map[string]string

func fetchTotals(base string) (totals, error) {
	resp, err := http.Get(base + "/totals")
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	var out totals
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, err
	}
	return out, nil
}

func reconcile(base string) {
	t, err := fetchTotals(base)
	if err != nil {
		log.Printf("reconcile: %v", err)
		return
	}
	sum := 0.0
	for _, raw := range t {
		var value float64
		fmt.Sscanf(raw, "%f", &value)
		sum += value
	}
	log.Printf("reconcile: %d accounts, drift %.4f", len(t), sum)
}

func main() {
	base := "http://127.0.0.1:7710"
	for {
		reconcile(base)
		time.Sleep(30 * time.Second)
	}
}
