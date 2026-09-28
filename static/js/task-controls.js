/* Progressive enhancement: original selects remain the submitted form controls. */
(() => {
  const root = document.querySelector('.tasks-page-shell');
  if (!root) return;
  let active = null;
  const icons = {todo:'list-check', progress:'lightning-charge', review:'eye', done:'check2-circle', low:'arrow-down-circle', normal:'dash-circle', high:'arrow-up-circle', urgent:'exclamation-circle', mine:'person-check', unassigned:'person-dash'};
  root.querySelectorAll('select:not([multiple])').forEach((select, index) => {
    if (select.disabled) return;
    const label = select.labels?.[0];
    const name = select.getAttribute('aria-label') || label?.textContent.trim() || 'Избор';
    const wrapper = document.createElement('div'); wrapper.className = 'task-select';
    select.before(wrapper); wrapper.append(select);
    select.classList.add('task-native-select'); select.tabIndex = -1;
    const button = document.createElement('button'); button.type = 'button'; button.className = 'task-select-trigger';
    button.setAttribute('aria-haspopup', 'listbox'); button.setAttribute('aria-expanded', 'false');
    const popup = document.createElement('div'); popup.className = 'task-select-popup'; popup.hidden = true;
    const list = document.createElement('div'); list.className = 'task-select-options'; list.id = `task-options-${index}`; list.setAttribute('role','listbox'); list.setAttribute('aria-label', name); list.tabIndex = -1;
    button.setAttribute('aria-controls',list.id);
    const search = document.createElement('input'); search.type='search'; search.className='task-select-search'; search.placeholder='Търси…'; search.setAttribute('aria-label', `Търси: ${name}`);
    if (select.options.length > 7) popup.append(search);
    popup.append(list); document.body.append(popup); wrapper.append(button);
    let cursor = 0, visible = [];
    const sync = () => {
      button.replaceChildren(); const icon = document.createElement('i'); icon.className=`bi bi-${icons[select.value] || (select.name === 'project' ? 'folder2' : select.name === 'assignee' ? 'person-circle' : 'sliders')}`; icon.setAttribute('aria-hidden','true');
      const text = document.createElement('span'); text.textContent=select.selectedOptions[0]?.textContent || 'Изберете…';
      const chevron = document.createElement('i'); chevron.className='bi bi-chevron-down task-select-chevron'; chevron.setAttribute('aria-hidden','true'); button.append(icon,text,chevron); button.setAttribute('aria-label',`${name}: ${text.textContent}`);
    };
    const close = (focus=false) => {popup.hidden=true;button.setAttribute('aria-expanded','false');if(active?.button===button)active=null;if(focus)button.focus();};
    const position = () => {const box=button.getBoundingClientRect();popup.style.width=`${Math.min(Math.max(box.width,210),window.innerWidth-24)}px`;popup.style.left=`${Math.max(12,Math.min(box.left,window.innerWidth-popup.offsetWidth-12))}px`;const below=window.innerHeight-box.bottom-14;const above=box.top-14;const height=Math.min(320,Math.max(below,above));popup.style.maxHeight=`${height}px`;popup.style.top=`${below>=Math.min(popup.scrollHeight,320)?box.bottom+6:Math.max(8,box.top-popup.offsetHeight-6)}px`;};
    const highlight = () => {visible.forEach((el,i)=>el.classList.toggle('focused',i===cursor));if(visible[cursor]){list.setAttribute('aria-activedescendant',visible[cursor].id);const row=visible[cursor];const top=row.offsetTop; if(top<popup.scrollTop)popup.scrollTop=top;else if(top+row.offsetHeight>popup.scrollTop+popup.clientHeight)popup.scrollTop=top+row.offsetHeight-popup.clientHeight;}};
    const choose = option => {select.value=option.value;sync();close(true);select.dispatchEvent(new Event('change',{bubbles:true}));};
    const render = () => {list.replaceChildren();visible=[];Array.from(select.options).forEach((option, i)=>{if(option.disabled || !option.textContent.toLocaleLowerCase().includes(search.value.toLocaleLowerCase()))return;const row=document.createElement('div');row.id=`task-option-${index}-${i}`;row.className='task-select-option';row.setAttribute('role','option');row.setAttribute('aria-selected',String(option.selected));const icon=document.createElement('i');icon.className=`bi bi-${icons[option.value] || 'circle'}`;const text=document.createElement('span');text.textContent=option.textContent;const check=document.createElement('i');check.className='bi bi-check2 task-option-check';row.append(icon,text,check);row.addEventListener('click',()=>choose(option));row._option=option;list.append(row);visible.push(row);});cursor=Math.max(0,visible.findIndex(el=>el.getAttribute('aria-selected')==='true'));if(!visible.length){const empty=document.createElement('p');empty.className='task-select-empty';empty.textContent='Няма резултати';list.append(empty);}highlight();};
    const open = () => {if(active)active.close();search.value='';popup.hidden=false;button.setAttribute('aria-expanded','true');active={button,close};render();position();(select.options.length>7?search:list).focus();};
    button.addEventListener('click',()=>popup.hidden?open():close());
    button.addEventListener('keydown',event=>{if(['ArrowDown','ArrowUp'].includes(event.key)){event.preventDefault();open();}});
    popup.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();close(true);}else if(event.key==='Tab'){close();button.focus();}else if(['ArrowDown','ArrowUp','Home','End'].includes(event.key)){event.preventDefault();cursor=event.key==='Home'?0:event.key==='End'?visible.length-1:Math.max(0,Math.min(visible.length-1,cursor+(event.key==='ArrowDown'?1:-1)));highlight();}else if(event.key==='Enter'){event.preventDefault();if(visible[cursor])choose(visible[cursor]._option);}});
    search.addEventListener('input',()=>{render();position();});
    select.addEventListener('change',sync);select.addEventListener('invalid',()=>button.focus());select.form?.addEventListener('reset',()=>setTimeout(sync,0));
    if(label)label.addEventListener('click',event=>{event.preventDefault();button.focus();});
    document.addEventListener('pointerdown',event=>{if(!popup.hidden&&!wrapper.contains(event.target)&&!popup.contains(event.target))close();});
    window.addEventListener('resize',()=>close());window.addEventListener('scroll',event=>{if(!popup.contains(event.target))close();},true);sync();
  });
})();
