(async window => {
  const peer=new RTCPeerConnection({iceServers:[]}),out={};
  try{
    const channel=peer.createDataChannel('audit',{ordered:true});
    peer.addTransceiver('audio',{direction:'recvonly'});peer.addTransceiver('video',{direction:'recvonly'});
    out.channel={label:channel.label,ordered:channel.ordered,protocol:channel.protocol,state:channel.readyState,tag:Object.prototype.toString.call(channel)};
    const offer=await peer.createOffer();const lines=offer.sdp.split('\r\n');
    out.offer={type:offer.type,sections:lines.filter(l=>l.startsWith('m=')).map(l=>l.slice(2).split(' ')[0]),
      mids:lines.filter(l=>l.startsWith('a=mid:')).map(l=>l.slice(6)),fingerprint:lines.some(l=>l.startsWith('a=fingerprint:sha-256 ')),
      setup:lines.filter(l=>l.startsWith('a=setup:')),data:lines.filter(l=>l.startsWith('a=sctp-port:'))};
    out.transceivers=peer.getTransceivers().map(t=>({direction:t.direction,kind:t.receiver.track.kind,current:t.currentDirection}));
    out.events=[];let completed;
    const done=new Promise(resolve=>{completed=resolve;setTimeout(()=>resolve('deadline'),5000)});
    peer.onicegatheringstatechange=()=>out.events.push('state:'+peer.iceGatheringState);
    peer.onicecandidate=e=>{if(!e.candidate){out.events.push('done');completed('complete')}else if(e.candidate.candidate==='')out.events.push('end:'+e.candidate.sdpMid);};
    await peer.setLocalDescription(offer);out.local=peer.localDescription.type;out.gathering=await done;
    out.state=peer.signalingState;
    return out;
  }catch(e){return {error:e.name,message:e.message}}finally{peer.close()}
})
