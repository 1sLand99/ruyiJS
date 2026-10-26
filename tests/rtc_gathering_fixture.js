globalThis.rtcResults = {};
globalThis.rtcPeers = [];
globalThis.startRtcCases = function() {
  for (const [name, steps] of Object.entries({
    dataFirst: ['data', 'audio', 'video'],
    mediaFirst: ['audio', 'video', 'data'],
    dataMiddle: ['audio', 'data', 'video'],
    mediaOnly: ['audio', 'video'],
    dataOnly: ['data', 'data'],
    legacyDataFirst: ['data', 'legacy'],
    closedData: ['closedData', 'audio']
  })) {
    const peer = new RTCPeerConnection({iceServers: []});
    rtcPeers.push(peer);
    const result = rtcResults[name] = {done: false, events: [], candidates: [], ends: [], sections: []};
    let offered;
    peer.onicegatheringstatechange = () => result.events.push('state:' + peer.iceGatheringState);
    peer.onicecandidate = event => {
      const candidate = event.candidate;
      if (candidate === null) {
        result.events.push('null:' + peer.iceGatheringState);
        result.done = true;
        return;
      }
      const value = {mid: candidate.sdpMid, index: candidate.sdpMLineIndex,
        sameObject: candidate === event.candidate,
        prototype: Object.getPrototypeOf(candidate) === RTCIceCandidate.prototype,
        eventPrototype: Object.getPrototypeOf(event) === RTCPeerConnectionIceEvent.prototype,
        trusted: event.isTrusted, target: event.target === peer,
        ufrag: candidate.usernameFragment === offered.ufrag};
      if (candidate.candidate === '') {
        result.ends.push(value);
        result.events.push('end:' + candidate.sdpMid + ':' + peer.iceGatheringState);
      } else {
        result.candidates.push({...value, component: candidate.candidate.split(' ')[1],
          protocol: candidate.candidate.split(' ')[2]});
      }
    };
    let legacy = false;
    for (const step of steps) {
      if (step === 'data') peer.createDataChannel('local');
      else if (step === 'closedData') peer.createDataChannel('local').close();
      else if (step === 'legacy') legacy = true;
      else peer.addTransceiver(step, {direction: 'recvonly'});
    }
    peer.createOffer(legacy ? {offerToReceiveAudio: true, offerToReceiveVideo: true} : {}).then(offer => {
      const lines = offer.sdp.split('\r\n');
      result.sections = lines.filter(line => line.startsWith('m=')).map(line => line.slice(2).split(' ')[0]);
      result.mids = lines.filter(line => line.startsWith('a=mid:')).map(line => line.slice(6));
      result.bundle = lines.find(line => line.startsWith('a=group:BUNDLE'));
      offered = {ufrag: lines.find(line => line.startsWith('a=ice-ufrag:')).slice(12)};
      return peer.setLocalDescription(offer);
    }).then(() => result.setLocalResolved = true).catch(error => {
      result.error = String(error); result.done = true;
    });
  }
  return null;
};
