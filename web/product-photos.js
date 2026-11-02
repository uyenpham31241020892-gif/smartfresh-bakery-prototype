const productImages=[{"sku": "TP-DN-001", "name": "Danish kem phô mai trái cây nhiệt đới", "url": "/assets/products/TP-DN-001.webp"}, {"sku": "TP-DN-002", "name": "Danish kem phô mai long nhãn", "url": "/assets/products/TP-DN-002.webp"}, {"sku": "TP-DN-003", "name": "Danish đào lệ chi", "url": "/assets/products/TP-DN-003.webp"}, {"sku": "TP-DN-004", "name": "Danish xoài chanh dây", "url": "/assets/products/TP-DN-004.webp"}, {"sku": "TP-CR-001", "name": "Croissant kem su hạt dẻ", "url": "/assets/products/TP-CR-001.webp"}, {"sku": "TP-CP-001", "name": "Crepe tiramisu Chấn Khang 80g", "url": "/assets/products/TP-CP-001.webp"}, {"sku": "TP-RV-001", "name": "Bánh red velvet A&C 60g", "url": "/assets/products/TP-RV-001.jpg"}];

function productPhoto(sku,name){const x=productImages.find(x=>x.sku===sku);return x?'<img class="sku-photo" src="'+x.url+'" alt="'+esc(name||x.name)+'" loading="lazy" width="64" height="64">':'';}
function decorateProductNames(){
 const root=document.getElementById('view');if(!root)return;
 const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);const matches=[];
 while(walker.nextNode()){const node=walker.currentNode;if(node.parentElement.closest('select,option,script,style,svg,[data-product-photo],.product-cell'))continue;
 const x=productImages.find(x=>node.textContent.includes(x.name));if(x)matches.push([node,x]);}
 for(const [node,x] of matches){if(!node.isConnected)continue;const span=document.createElement('span');span.dataset.productPhoto=x.sku;span.className='sku-photo-label';const img=document.createElement('img');img.src=x.url;img.alt=x.name;img.width=56;img.height=56;img.loading='lazy';img.className='sku-photo';span.append(img,document.createTextNode(node.textContent));node.replaceWith(span);
 const icon=span.parentElement.querySelector('.product-icon');if(icon)icon.remove();}
}
let photoScheduled=false;
new MutationObserver(()=>{if(photoScheduled)return;photoScheduled=true;requestAnimationFrame(()=>{photoScheduled=false;decorateProductNames();});}).observe(document.getElementById('view'),{childList:true,subtree:true});
