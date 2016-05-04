function resize(argument) {
	//$("").height($(window).height() - ($("#results").position().top + 10));
}

function get(url) {
	return Promise.resolve($.get(url).fail(function(e) { return e })).catch(function(e) { throw e });
}

function summonerTableViewCell(ezInfo, mastery) {
	// ...I wish I was a designer. But I ain't got the time!
	return `
	<div class="clearfix summoner-cell">
		<div class="float-left">
			<img src="http://ddragon.leagueoflegends.com/cdn/6.8.1/img/champion/${ezInfo.champ_key}.png">
		</div>
		<div class="float-left pad-lefty">
			<h4 class="champ-title"> ${ezInfo.summoner_name} </h4>
			<h5 class="champ-title"> ${ezInfo.champ_name} </h5>
			<p> Champion Level: ${mastery ? mastery.championLevel : "First Timer"} </p>
		</div>
	</div>`;
}

$(document).ready(function() {
	// Hack the crap out of sizing the results view
	resizeResults();
	$(window).resize(resize);
});