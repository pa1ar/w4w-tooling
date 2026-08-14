import { NextResponse } from "next/server";
import { readBroadBatchGeojson } from "@/lib/broad-batches";
import { mapboxToken } from "@/lib/paths";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ batchId: string }> },
) {
  const { batchId } = await params;
  const geojson = await readBroadBatchGeojson(Number(batchId));
  if (!geojson) return new NextResponse("Not found", { status: 404 });

  const data = JSON.stringify(geojson).replaceAll("<", "\\u003c");
  const token = JSON.stringify(mapboxToken(false));
  const html = `<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link href="https://api.mapbox.com/mapbox-gl-js/v3.21.0/mapbox-gl.css" rel="stylesheet">
<script src="https://api.mapbox.com/mapbox-gl-js/v3.21.0/mapbox-gl.js"></script>
<style>
html,body,#map{height:100%;margin:0;background:#0B1410}*{box-sizing:border-box}
.mapboxgl-popup-content{background:#1D2622;color:#EAFFF5;border:1px solid rgba(255,255,255,.14);border-radius:10px;font:12px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;padding:10px 12px}.mapboxgl-popup-tip{border-top-color:#1D2622!important;border-bottom-color:#1D2622!important}.mapboxgl-popup-content a{color:#8ECE90}.mapboxgl-ctrl-attrib,.mapboxgl-ctrl-attrib a{background:rgba(11,20,16,.72)!important;color:#91AA9D!important}
</style></head><body><div id="map"></div><script>
mapboxgl.accessToken=${token};
const data=${data};
const map=new mapboxgl.Map({container:'map',style:'mapbox://styles/mapbox/dark-v11',center:[24.75,59.44],zoom:11});
map.addControl(new mapboxgl.NavigationControl({showCompass:false}),'top-right');
map.on('load',()=>{
  map.addSource('candidates',{type:'geojson',data});
  map.addLayer({id:'candidate-halo',type:'line',source:'candidates',paint:{'line-color':'#0B1410','line-width':7,'line-opacity':.8}});
  map.addLayer({id:'candidates',type:'line',source:'candidates',paint:{'line-color':['match',['get','proposed_value'],'bad','#F8D1DC','#F1FFBC'],'line-width':4,'line-opacity':.92}});
  const bounds=new mapboxgl.LngLatBounds();
  for(const feature of data.features){for(const coordinate of feature.geometry.coordinates)bounds.extend(coordinate)}
  if(!bounds.isEmpty())map.fitBounds(bounds,{padding:36,maxZoom:15,duration:0});
  map.on('mouseenter','candidates',()=>map.getCanvas().style.cursor='pointer');
  map.on('mouseleave','candidates',()=>map.getCanvas().style.cursor='');
  map.on('click','candidates',(event)=>{
    const p=event.features[0].properties;
    new mapboxgl.Popup().setLngLat(event.lngLat).setHTML(
      '<strong>#'+p.rank+' · way '+p.way_id+'</strong><br>'+p.highway+' · '+p.proposed_value+'<br>'+p.coverage_pct+'% coverage · '+p.rides+' rides<br><a target="_blank" href="https://www.openstreetmap.org/way/'+p.way_id+'">open OSM ↗</a> · <a target="_blank" href="https://www.openstreetmap.org/edit?way='+p.way_id+'">open iD ↗</a>'
    ).addTo(map);
  });
});
</script></body></html>`;

  return new NextResponse(html, {
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}
